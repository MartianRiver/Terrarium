# The coordinator's state on disk: content-addressed blobs (code bundles,
# overlays, configs, parent brains, results) and one JSON file per job. A job
# goes pending → running → done, or back to pending when its lease runs out
# or its worker gives up, and failed after MAX_ATTEMPTS (at once when the
# brain ended its own run). The coordinator never looks inside a job beyond
# what scheduling needs: a job is signed on River's machine and every worker
# checks that signature itself (jobs.py).

import hashlib
import io
import json
import os
import tarfile
import threading
import time
from pathlib import Path

from .log import Logger

log = Logger('store')

# a worker beats every minute, so a job comes back about five minutes after its worker vanishes
LEASE = 300
MAX_ATTEMPTS = 2
STATES = ('pending', 'running', 'done', 'failed', 'cancelled')
# why a job failed: the brain ending its own run (train's stuck and give_up guards), which another try with the
# same seed would only repeat, or the machine: training crashed, the job couldn't be set up, or the worker went
# quiet and its lease ran out
KINDS = {'stuck': 'stuck', 'give_up': 'gave up', 'crash': 'failed', 'setup': 'failed', 'quiet': 'lease ran out'}
BRAIN = ('stuck', 'give_up')
# what a job can ask of the machine that runs it, checked against what the worker says it is; gpu = false keeps a
# job off machines with a GPU, so CPU work leaves them free
NEEDS = {'gpu': bool, 'gpu_memory_gb': (int, float), 'cores': int, 'memory_gb': (int, float), 'machine': str}
# the first worker version that knows a score job; an older one would take it and fail it
SCORE_VERSION = 10
# wiping a brain's notes on the game's event: an older worker would drop it and score with the notes kept
SCORE_EVENT_VERSION = 13


def scoring(spec: dict) -> bool:
    return spec.get('kind') == 'score'


def has_gpu(specs: dict | None) -> bool:
    return bool((specs or {}).get('gpus')) or bool((specs or {}).get('mps'))


def bad_needs(needs) -> str | None:
    if not isinstance(needs, dict) or not needs:
        return 'needs is a table of ' + ', '.join(NEEDS)
    for key, value in needs.items():
        if key not in NEEDS:
            return f'unknown need {key!r}'
        if not isinstance(value, NEEDS[key]) or (isinstance(value, bool) and NEEDS[key] is not bool):
            return f'need {key} has the wrong type'
    return None


def unmet(needs: dict | None, name: str, specs: dict | None) -> str | None:
    """The first need a machine doesn't meet, or None when it meets them all."""
    if not needs:
        return None
    specs = specs or {}
    gpus = specs.get('gpus') or []
    # a Mac's GPU shares the machine's memory
    gpu_memory = max([g.get('memory_gb') or 0 for g in gpus] + [specs.get('memory_gb') or 0 if specs.get('mps') else 0])
    gpu = has_gpu(specs)
    if 'machine' in needs and needs['machine'] != name:
        return f'machine {needs["machine"]}'
    if needs.get('gpu') is True and not gpu:
        return 'a GPU'
    if needs.get('gpu') is False and gpu:
        return 'no GPU'
    if 'gpu_memory_gb' in needs and gpu_memory < needs['gpu_memory_gb']:
        return f'gpu_memory_gb >= {needs["gpu_memory_gb"]:g}'
    for key in ('cores', 'memory_gb'):
        if key in needs and (specs.get(key) or 0) < needs[key]:
            return f'{key} >= {needs[key]:g}'
    return None


class Gone(LookupError):
    """The job isn't this worker's any more: done elsewhere, cancelled, or its lease ran out and it went to another."""


class Full(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: Path, data: bytes):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def member(tar: tarfile.TarFile, name) -> bytes:
    f = tar.extractfile(name)
    if f is None:
        raise ValueError(f'{name} is not a file')
    return f.read()


def final_checkpoint(result: bytes) -> bytes:
    """The checkpoint a finished run names in its run.json, out of the run's tar.gz."""
    with tarfile.open(fileobj=io.BytesIO(result), mode='r:gz') as tar:
        names = {m.name: m for m in tar.getmembers() if m.isfile()}
        record = next((n for n in names if n.count('/') == 1 and n.endswith('/run.json')), None)
        if record is None:
            raise ValueError('result has no run.json')
        run = record.split('/')[0]
        checkpoint = json.loads(member(tar, names[record]))['checkpoint']
        found = names.get(f'{run}/checkpoints/{checkpoint}')
        if found is None or '/' in checkpoint:
            raise ValueError(f'result has no checkpoints/{checkpoint}')
        return member(tar, found)


class Store:
    def __init__(self, root: Path, results_cap: int = 8_000_000_000):
        self.root = Path(root)
        self.blobs = self.root / 'blobs'
        self.jobs = self.root / 'jobs'
        for d in (self.blobs, self.jobs):
            d.mkdir(parents=True, exist_ok=True)
        self.results_cap = results_cap
        self.lock = threading.Lock()

    # blobs

    def has(self, digest: str) -> bool:
        return (self.blobs / digest).exists()

    def put(self, data: bytes) -> str:
        digest = sha256(data)
        if not self.has(digest):
            write_atomic(self.blobs / digest, data)
        return digest

    def get(self, digest: str) -> bytes:
        if not (len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)) or not self.has(digest):
            raise KeyError(digest)
        return (self.blobs / digest).read_bytes()

    def results_size(self) -> int:
        return sum((self.blobs / j['result']).stat().st_size for j in self.all() if j.get('result'))

    # jobs

    def read(self, id: str) -> dict:
        path = self.jobs / f'{id}.json'
        if not id.isalnum() or not path.exists():
            raise KeyError(id)
        return json.loads(path.read_text())

    def save(self, job: dict):
        write_atomic(self.jobs / f'{job["spec"]["id"]}.json', (json.dumps(job, indent=1) + '\n').encode())

    def all(self) -> list[dict]:
        jobs = [json.loads(p.read_text()) for p in self.jobs.glob('*.json')]
        return sorted(jobs, key=lambda j: (j['spec']['added'], j['spec']['id']))

    def add(self, spec: dict, sig: str, now: float | None = None) -> dict:
        with self.lock:
            if (self.jobs / f'{spec["id"]}.json').exists():
                raise ValueError(f'job {spec["id"]} already exists')
            missing = [d for d in blobs_of(spec) if not self.has(d)]
            if missing:
                raise ValueError(f'blobs not uploaded yet: {missing}')
            parent = spec.get('parent') or {}
            if 'job' in parent:
                self.read(parent['job'])
            job = {'spec': spec, 'sig': sig, 'state': 'pending', 'attempts': 0, 'worker': None, 'lease': None,
                   'progress': None, 'result': None, 'final': None, 'error': None,
                   'history': [[now or time.time(), 'added']]}
            self.save(job)
            log.info('job added', id=spec['id'], name=spec['name'], batch=spec['batch'], trusted=spec['trusted'])
            return job

    def ready(self, job: dict) -> bool:
        parent = job['spec'].get('parent') or {}
        return 'job' not in parent or self.read(parent['job'])['state'] == 'done'

    def blocked(self, job: dict) -> bool:
        """A pending job whose parent job can never finish."""
        parent = job['spec'].get('parent') or {}
        return job['state'] == 'pending' and 'job' in parent and \
            self.read(parent['job'])['state'] in ('failed', 'cancelled')

    def parent_blob(self, job: dict) -> str | None:
        parent = job['spec'].get('parent') or {}
        if 'blob' in parent:
            return parent['blob']
        if 'job' in parent:
            return self.read(parent['job'])['final']
        return None

    def expire(self, now: float):
        for job in self.all():
            if job['state'] == 'running' and job['lease'] < now:
                job['kind'] = 'quiet'
                self.release(job, now, KINDS['quiet'])

    def release(self, job: dict, now: float, why: str, again: bool = True):
        job['state'] = 'pending' if again and job['attempts'] < MAX_ATTEMPTS else 'failed'
        job['history'].append([now, f'{why} on {job["worker"]}'])
        log.warn('job released', id=job['spec']['id'], worker=job['worker'], why=why, state=job['state'])
        job['worker'], job['lease'] = None, None
        self.save(job)
        self.unpeek(job['spec']['id'])

    def fits(self, job: dict, worker: str, trusted: bool, role: str | None, specs: dict | None,
             version: int | None) -> bool:
        spec = job['spec']
        if job['state'] != 'pending' or (spec['trusted'] and not trusted) or not self.ready(job):
            return False
        if spec.get('on') not in (None, role) or unmet(spec.get('needs'), worker, specs):
            return False
        if scoring(spec):
            # a pod is paid by the hour for its GPU: it scores only what's kept to rented machines
            need = SCORE_EVENT_VERSION if spec['score'].get('wiped_on_event') else SCORE_VERSION
            return (version or 0) >= need and (role != 'rented' or spec.get('on') == 'rented')
        return True

    def claim(self, worker: str, trusted: bool, now: float | None = None, role: str | None = None,
              specs: dict | None = None, version: int | None = None) -> dict | None:
        """The oldest job this worker may take, but the oldest of the kind it's best at first: training for a machine
        with a GPU, scoring (which plays games on the CPU) for one without, so neither waits behind the other."""
        now = now or time.time()
        with self.lock:
            self.expire(now)
            fit = [j for j in self.all() if self.fits(j, worker, trusted, role, specs, version)]
            best = [j for j in fit if scoring(j['spec']) != has_gpu(specs)]
            for job in (best or fit)[:1]:
                job |= {'state': 'running', 'worker': worker, 'lease': now + LEASE, 'progress': None,
                        'attempts': job['attempts'] + 1}
                job['history'].append([now, f'claimed by {worker}'])
                self.save(job)
                log.info('job claimed', id=job['spec']['id'], worker=worker, attempt=job['attempts'])
                return job
        return None

    def mine(self, id: str, worker: str) -> dict:
        job = self.read(id)
        if job['state'] != 'running' or job['worker'] != worker:
            raise Gone(id)
        return job

    def beat(self, id: str, worker: str, progress: dict | None = None, now: float | None = None):
        now = now or time.time()
        with self.lock:
            job = self.mine(id, worker)
            job['lease'] = now + LEASE
            if progress is not None:
                job['progress'] = progress
            self.save(job)

    def finish(self, id: str, worker: str, result: bytes, now: float | None = None):
        """A run's tar.gz. Taken from whoever last claimed the job, even past its lease, as long as nobody
        else has it now: a run that took a while to upload is still a good run."""
        now = now or time.time()
        with self.lock:
            job = self.read(id)
            claimed = job['history'] and any(h[1] == f'claimed by {worker}' for h in job['history'])
            if job['state'] in ('done', 'cancelled') or not claimed or \
                    (job['state'] == 'running' and job['worker'] != worker):
                raise Gone(id)
            if self.results_size() + len(result) > self.results_cap:
                raise Full(f'results are over {self.results_cap} bytes; sync and prune them')
            # a score job's result is its scores, no brain
            final = None if scoring(job['spec']) else final_checkpoint(result)
            job |= {'state': 'done', 'result': self.put(result), 'final': final and self.put(final), 'lease': None,
                    'worker': worker, 'error': None, 'kind': None}
            job['history'].append([now, f'done by {worker}'])
            self.save(job)
            self.unpeek(id)
            log.info('job done', id=id, worker=worker, bytes=len(result))

    def peek(self, id: str, worker: str, data: bytes):
        """A running job's run so far, from the worker holding it; one a job, the newest kept."""
        with self.lock:
            self.mine(id, worker)
            write_atomic(self.jobs / f'{id}.peek', data)

    def peeked(self, id: str) -> bytes:
        path = self.jobs / f'{id}.peek'
        if not id.isalnum() or not path.exists():
            raise KeyError(id)
        return path.read_bytes()

    def unpeek(self, id: str):
        (self.jobs / f'{id}.peek').unlink(missing_ok=True)

    def fail(self, id: str, worker: str, error: str, kind: str | None = None, now: float | None = None):
        now = now or time.time()
        kind = kind if kind in KINDS else 'crash'
        with self.lock:
            job = self.mine(id, worker)
            job['error'], job['kind'] = error[-4000:], kind
            self.release(job, now, KINDS[kind], again=kind not in BRAIN)

    def give_back(self, id: str, worker: str, now: float | None = None):
        """A worker that's stopping hands a job back; that doesn't count as an attempt."""
        now = now or time.time()
        with self.lock:
            job = self.mine(id, worker)
            job['attempts'] -= 1
            self.release(job, now, 'given back')

    def restarted(self, worker: str, now: float | None = None) -> list[str]:
        """A worker starting up holds nothing, whatever the jobs say: hand back what it had, not as an attempt."""
        held = [j['spec']['id'] for j in self.all() if j['state'] == 'running' and j['worker'] == worker]
        for id in held:
            self.give_back(id, worker, now)
        return held

    def cancel(self, id: str, now: float | None = None):
        with self.lock:
            job = self.read(id)
            if job['state'] in ('pending', 'running'):
                job |= {'state': 'cancelled', 'worker': None, 'lease': None}
                job['history'].append([now or time.time(), 'cancelled'])
                self.save(job)
                self.unpeek(id)

    def retry(self, id: str, now: float | None = None):
        with self.lock:
            job = self.read(id)
            if job['state'] in ('failed', 'cancelled'):
                job |= {'state': 'pending', 'attempts': 0, 'error': None}
                job['history'].append([now or time.time(), 'retried'])
                self.save(job)


def blobs_of(spec: dict) -> list[str]:
    code = spec['code']
    found = [spec['world'], spec.get('train'), code.get('bundle'), code.get('overlay'), (spec.get('parent') or {}).get('blob')]
    return [d for d in found if d]
