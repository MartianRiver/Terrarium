# A machine that trains for the queue: asks the coordinator for a job, checks
# it, builds the job's code, runs terrarium.train in it (terrarium.games for a
# score job) and uploads the run.
#
#   uv run python -m terrarium.worker --server URL [--slots N] [--trusted] [--paused] [--anytime]
#   uv run python -m terrarium.worker pause | resume | drain | status
#   uv run python -m terrarium.worker calibrate   (how many jobs this machine should run at once)
#
# Before a job runs, every one of these has to hold (docs/compute.md):
#   - its spec is signed by a key in sim/allowed_signers (this checkout's copy, not the server's)
#   - every input matches the sha256 the signed spec names
#   - without --trusted: the code is fetched from the public repo by this worker, and only run
#     if it's on one of its branches; bundles and overlays (uncommitted code) are refused
# The server can't send commands; all it can say is "this signed job, please".
#
# Everything lives in --home (~/.terrarium/worker): the token, settings.toml, a
# checkout per commit, each job's inputs and log, and the runs this machine
# made. The status page and pause/resume listen on 127.0.0.1 only.
#
# On a lent machine the worker keeps out of the way (machine.py): it trains only
# when the machine has been left alone for a while and is on mains, at half the
# CPU and low priority, pauses the job when someone comes back or the GPU runs
# hot, and gives it back to the queue when a game starts. --anytime (and
# --instance, a rented machine) turns that off.

import argparse
import importlib
import io
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil

from . import calibrate, jobs, machine, runs, snapshot, usage
from .log import Logger
from .store import scoring, sha256
from .trust import KEEP_CODE, Refused, capped, check_lock, job_env, pin_signers, scrub, utc

log = Logger('worker')

HOME = jobs.HOME / 'worker'
PORT = 5191
POLL = 30
BEAT = 60
# the run so far goes up this often while training, so the channel can show a run before it's done
PEEK = 900
# the wait between looks when jobs are running and a free slot found nothing to claim
BUSY = 5
# 13: score jobs can wipe on the game's event (a worker before it would score them with the notes kept)
# 14: training jobs can ask for fast and gpu_collect (a worker before it would train them the slow way)
VERSION = 14


def cpus() -> int:
    # containers report the host's cores; the cgroup quota is what this one may use
    return runs.cpu_quota() or os.cpu_count() or 1


def shares(slots: int, rules: machine.Rules, rollouts: int | None = None) -> tuple[int, int]:
    """The threads and rollout processes each of `slots` jobs gets."""
    share = max(1, int(cpus() * rules.cpu) // slots)
    return share, rollouts or max(1, min(8, share - 1))


def cap(cmd: list[str], slots: int, rules: machine.Rules) -> list[str]:
    return capped(cmd, cpus() * rules.cpu / slots, cpus())


def specs() -> dict:
    """What this machine is, for the coordinator's board. Read once, at start."""
    gpus = []
    if smi := shutil.which('nvidia-smi'):
        for line in machine.run([smi, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits']).splitlines():
            name, _, mb = line.rpartition(',')
            if name.strip() and mb.strip().isdigit():
                gpus.append({'name': name.strip(), 'memory_gb': round(int(mb.strip()) / 1024)})
    try:
        cpu, memory = runs.cpu(), runs.memory_gb()
    except (OSError, ValueError):
        cpu, memory = platform.processor(), None
    out = {'os': f'{platform.system()} {platform.release()}', 'cpu': cpu, 'cores': os.cpu_count(),
           'memory_gb': memory, 'gpus': gpus}
    # an Apple-silicon Mac trains on its own GPU (torch's mps), which nvidia-smi doesn't see
    if sys.platform == 'darwin' and platform.machine() == 'arm64':
        out['mps'] = True
    return out


def torch_extra() -> list[str]:
    # torch comes from PyPI only on macOS; elsewhere it's the cpu or cuda extra (pyproject.toml)
    if sys.platform == 'darwin':
        return []
    return ['--extra', 'cuda' if shutil.which('nvidia-smi') else 'cpu']


def code_key(spec: dict) -> str:
    """The folder in code/ a job's checkout is built in: one per commit and overlay."""
    c = spec['code']
    return c['commit'][:12] + (f'-{c["overlay"][:12]}' if c['overlay'] else '')


def has_triton() -> bool:
    try:
        importlib.import_module('triton')
    except ImportError:
        return False
    return True


def python(sim: Path) -> Path:
    return sim / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')


def sync(sim: Path):
    subprocess.run(['uv', 'sync', '-q', '--locked', *torch_extra()], cwd=sim, check=True, capture_output=True,
                   env=job_env())


class Task:
    def __init__(self, job: dict):
        self.spec, self.sig, self.parent = job['spec'], job['sig'], job.get('parent')
        self.id = self.spec['id']
        self.state, self.reason = 'preparing', ''
        self.proc: subprocess.Popen | None = None
        self.run: Path | None = None
        self.gone = threading.Event()
        self.started = time.time()
        self.paused_at: float | None = None
        self.paused = 0.0
        # the most other jobs this one ran beside, for checking the machine's calibration against real jobs
        self.beside = 0
        # fast and gpu_collect as the job ran them, for a training job (the machine may have dropped what it asked)
        self.ran: dict | None = None
        self.peeked = time.time()
        # the coordinator has the run: a beat now would get 410 and read as the job taken away
        self.uploaded = False

    def progress(self) -> dict:
        p = {'state': self.state, 'reason': self.reason, 'samples': 0, 'samples_per_second': None}
        if self.run and (self.run / 'metrics.jsonl').exists():
            rows = [r for r in usage.rows_of(self.run) if 'samples' in r and 'samples_per_second' in r]
            if rows:
                p |= {'samples': rows[-1]['samples'], 'samples_per_second': rows[-1]['samples_per_second']}
        return p

    def usage(self) -> dict | None:
        """Where its training time goes lately, and what holds it back (terrarium.usage)."""
        if self.state != 'training' or not self.run or not (self.run / 'metrics.jsonl').exists():
            return None
        recent = usage.recent(usage.rows_of(self.run))
        try:
            record = json.loads((self.run / 'run.json').read_text())
        except (OSError, ValueError):
            record = {}
        return recent | {'held_back': usage.held_back(recent, record)} if recent else None

    def job_record(self) -> dict:
        return {'spec': self.spec, 'sig': self.sig, 'beside': self.beside, **({'ran': self.ran} if self.ran else {})}

    def summary(self) -> dict:
        return {'id': self.id, 'name': self.spec['name'], 'batch': self.spec['batch'], 'total': self.spec['samples'],
                'since': self.started, **self.progress()}


def failure_kind(task: Task) -> str:
    """Whether a failed job's brain ended its own run (train's stuck and give_up guards) or the machine let it down,
    so a pod isn't blamed for a seed that collapsed."""
    if task.state == 'preparing':
        return 'setup'
    try:
        record = json.loads((task.run / 'run.json').read_text()) if task.run else {}
    except (OSError, ValueError):
        record = {}
    if 'stuck' in record:
        return 'stuck'
    if 'gave_up' in record:
        return 'give_up'
    return 'crash'


class Worker:
    def __init__(self, client: jobs.Client, home: Path = HOME, slots: int = 1, trusted: bool = False,
                 paused: bool = False, rollouts: int | None = None, max_load: float | None = None,
                 instance: int | None = None, repo: str = '', signers: Path = jobs.SIGNERS, command=None,
                 scorer=None, rules: machine.Rules = machine.Rules.anytime(), watch: machine.Watch | None = None):
        self.client, self.home, self.slots, self.trusted = client, Path(home), slots, trusted
        self.paused, self.draining, self.stopping = paused, False, threading.Event()
        self.peeks = True
        self.rules, self.watch = rules, watch or machine.Watch(rules)
        self.awake = machine.Awake()
        self.verdict = machine.Verdict('go', '')
        self.threads, self.rollouts = shares(slots, rules, rollouts)
        # a score job has the whole machine to itself
        self.whole = max(1, int(cpus() * rules.cpu))
        self.score_waits = False
        self.max_load, self.instance, self.repo, self.signers = max_load, instance, repo, signers
        self.command, self.scorer = command or self.train_command, scorer or self.score_command
        self.tasks: dict[str, Task] = {}
        self.specs = specs()
        self.lock = threading.Lock()
        self.building: dict[str, threading.Lock] = {}
        for d in ('code', 'jobs', 'runs'):
            (self.home / d).mkdir(parents=True, exist_ok=True)

    # the loop

    def loop(self):
        last_beat = 0.0
        log.info('worker started', slots=self.slots, trusted=self.trusted, paused=self.paused,
                 rollouts=self.rollouts, threads=self.threads, platform=platform.platform(), rules=self.rules)
        self.hello()
        # read the machine once before the first claim, not just in the guard's own time
        self.mind()
        threading.Thread(target=self.guard, name='guard', daemon=True).start()
        while not self.stopping.is_set():
            if time.time() - last_beat >= BEAT:
                self.beat()
                self.report()
                last_beat = time.time()
            if self.draining and not self.tasks:
                break
            asked = self.wants_work()
            if asked:
                try:
                    job = self.client.json('POST', '/api/claim', self.info())
                except (urllib.error.URLError, OSError, RuntimeError) as e:
                    log.warn('claim failed', error=str(e))
                    job = None
                if job and job['spec']['id'] in self.tasks:
                    self.keep(job)
                    job = None
                if job and scoring(job['spec']) and self.tasks:
                    # the queue can't tell it what's already running here, so a score job that arrives
                    # beside a training one goes back, and nothing is claimed until the machine is empty
                    self.hand_back(Task(job), 'a score job takes the whole machine')
                    self.score_waits, job = True, None
                if job:
                    self.start(job)
                    continue
            self.stopping.wait(POLL if asked or not self.tasks else BUSY)

    def hello(self):
        while not self.stopping.is_set():
            try:
                returned = self.client.json('POST', '/api/hello', self.info())['returned']
                if returned:
                    log.info('handed back jobs from before a restart', jobs=returned)
                return
            except (urllib.error.URLError, OSError, RuntimeError) as e:
                log.warn('no answer from the coordinator yet, trying again', error=str(e))
                self.stopping.wait(POLL)

    def wants_work(self) -> bool:
        if self.paused or self.draining or len(self.tasks) >= self.slots or self.verdict.action != 'go':
            return False
        # a score job has the machine: nothing else starts beside it, and it starts only on an empty one
        if any(scoring(t.spec) for t in list(self.tasks.values())):
            return False
        if self.score_waits:
            if self.tasks:
                return False
            self.score_waits = False
        # psutil's works on Windows too, where it's estimated from the processor queue
        if self.max_load is not None and (load := psutil.getloadavg()[0]) > self.max_load:
            log.debug('busy machine, not claiming', load=load, max=self.max_load)
            return False
        return True

    def info(self) -> dict:
        state, reason = self.state()
        if not self.trusted and self.instance is None:
            # why a lent machine is waiting (someone at it, a game on) stays on it
            reason = ''
        training = [u for t in list(self.tasks.values()) if (u := t.usage())]
        return {'platform': platform.platform(), 'slots': self.slots, 'trusted': self.trusted, 'version': VERSION,
                'specs': self.specs, 'state': state, 'reason': reason, 'usage': training[0] if training else None}

    def report(self):
        # every minute, working or not, so the coordinator knows a waiting machine is still there
        try:
            self.client.json('POST', '/api/status', self.info())
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            log.warn('status report failed', error=str(e))

    def keep(self, job: dict):
        """The queue offered a job this process is already running (its lease ran out while beats failed, say, and it
        went back to the front): the server now lists it as ours again, so the running attempt stays and a beat says so.
        A second attempt would clear the first one's run folder."""
        task = self.tasks.get(job['spec']['id'])
        if task and not task.gone.is_set():
            log.warn('job offered again while still running here, keeping the running attempt', id=task.id)
            self.beat()
        else:
            self.hand_back(Task(job), 'its first attempt here is still stopping')

    def start(self, job: dict):
        task = Task(job)
        with self.lock:
            if task.id in self.tasks:
                log.warn('job already running here, not starting it twice', id=task.id)
                return
            self.tasks[task.id] = task
        threading.Thread(target=self.work, args=(task,), name=f'job-{task.id}', daemon=True).start()

    def beat(self):
        for task in list(self.tasks.values()):
            if task.uploaded:
                continue
            try:
                self.client.json('POST', f'/api/jobs/{task.id}/beat', {'progress': task.progress()})
            except RuntimeError as e:
                if ' 410 ' in str(e):
                    log.warn('job taken away', id=task.id)
                    task.gone.set()
                    # the whole tree: rollout and eval processes left behind would hold the GPU, and
                    # look like another program using it
                    if task.proc and task.proc.poll() is None:
                        machine.kill(task.proc.pid)
            except (urllib.error.URLError, OSError) as e:
                log.warn('beat failed', id=task.id, error=str(e))
            if self.peeks and task.state == 'training' and task.run and time.time() - task.peeked >= PEEK:
                self.peek(task)

    def peek(self, task: Task):
        task.peeked = time.time()
        assert task.run
        try:
            status, body = self.client.call('PUT', f'/api/jobs/{task.id}/peek', peek(task.run))
        except (urllib.error.URLError, OSError, ValueError) as e:
            log.warn('peek not sent', id=task.id, error=str(e))
            return
        if status == 404:
            # a coordinator from before peeks: stop asking until this worker restarts
            log.warn('coordinator takes no peeks', id=task.id)
            self.peeks = False
        elif status != 200:
            log.warn('peek refused', id=task.id, status=status, body=body[:200])

    def stop(self):
        """Hand every unfinished job back and stop; a job given back doesn't count against it."""
        self.stopping.set()
        for task in list(self.tasks.values()):
            if task.state in ('preparing', 'training', 'scoring', 'paused'):
                self.hand_back(task, 'worker stopping')

    def hand_back(self, task: Task, reason: str):
        task.gone.set()
        task.state, task.reason = 'handed back', reason
        if task.proc and task.proc.poll() is None:
            machine.kill(task.proc.pid)
        try:
            self.client.json('POST', f'/api/jobs/{task.id}/return')
            log.info('job handed back', id=task.id, reason=reason)
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            log.warn('could not give a job back; its lease will run out', id=task.id, error=str(e))

    # keeping out of the owner's way

    def guard(self):
        while not self.stopping.is_set():
            try:
                self.mind()
            except Exception as e:
                log.error('machine check failed', error=repr(e), exc=True)
            self.stopping.wait(machine.EVERY)

    def mind(self, now: float | None = None):
        now = time.time() if now is None else now
        training = [(t, t.proc.pid) for t in list(self.tasks.values())
                    if t.proc and t.proc.poll() is None and not t.gone.is_set()]
        ours = frozenset(p.pid for _, pid in training for p in machine.tree(pid))
        verdict = self.watch.check(ours, now)
        if self.paused and verdict.action == 'go':
            verdict = machine.Verdict('pause', 'paused from the status page')
        if verdict != self.verdict:
            log.info('machine', action=verdict.action, reason=verdict.reason)
        self.verdict = verdict
        for task, pid in training:
            if verdict.action == 'stop':
                self.hand_back(task, verdict.reason)
            elif verdict.action == 'pause':
                if task.paused_at is None:
                    machine.suspend(pid)
                    task.paused_at, task.state = now, 'paused'
                    log.info('job paused', id=task.id, reason=verdict.reason)
                task.reason = verdict.reason
                if now - task.paused_at > self.rules.suspended * 60:
                    self.hand_back(task, f'paused over {self.rules.suspended:g} min')
            elif (since := task.paused_at) is not None:
                machine.resume(pid)
                task.paused += now - since
                task.paused_at, task.state, task.reason = None, 'scoring' if scoring(task.spec) else 'training', ''
                log.info('job resumed', id=task.id)
        # a paused job lets it sleep: on battery, or with someone at it, sleep is the owner's call
        self.awake.hold(self.rules.keep_awake and any(t.state in ('preparing', 'training', 'scoring')
                                                      and not t.gone.is_set()
                                                      for t in list(self.tasks.values())))
        self.note_beside()

    def note_beside(self):
        going = [t for t in list(self.tasks.values()) if t.state in ('training', 'scoring') and not t.gone.is_set()]
        for t in going:
            t.beside = max(t.beside, len(going) - 1)

    # one job

    def work(self, task: Task):
        dir = self.home / 'jobs' / task.id
        try:
            inputs = self.prepare(task, dir)
            code = self.code(task.spec)
            task.state = 'scoring' if scoring(task.spec) else 'training'
            log.info(task.state, id=task.id, name=task.spec['name'], code=code.name)
            runs = code / 'runs' / ('scores' if scoring(task.spec) else '')
            # half a run from an attempt that was stopped would be mistaken for this one
            live = {t.run for t in list(self.tasks.values()) if t is not task}
            for old in runs.glob(f'*-{jobs.run_name(task.spec)}'):
                if old not in live:
                    shutil.rmtree(old)
            # relative, so the paths run.json records don't carry this machine's home folder
            rel = {k: Path(os.path.relpath(v, code / 'sim')) for k, v in inputs.items()}
            (self.score if scoring(task.spec) else self.train)(task, rel, code / 'sim', runs, dir)
            if self.stopping.is_set() or task.gone.is_set():
                return
            assert task.run
            task.state = 'uploading'
            (task.run / 'job.json').write_text(json.dumps(task.job_record(), indent=1) + '\n')
            if task.spec['code']['overlay']:
                # diff.patch has tracked changes and untracked.txt only names; this is the code itself
                (task.run / 'overlay.tar.gz').write_bytes(self.blob(task.spec['code']['overlay']))
            lent = not self.trusted and self.instance is None
            # a score's machine and times are in its score.json; it has no run.json to add them to
            extra = (None, 0, False) if scoring(task.spec) else (self.instance, task.paused, lent)
            self.upload(task, pack(task.run, *extra))
            # kept, so the owner can see what their machine made
            shutil.move(task.run, self.home / 'runs' / task.run.name)
            prune(self.home / 'runs', self.rules.keep_gb)
            shutil.rmtree(dir / 'inputs', ignore_errors=True)
            task.state = 'done'
        except Exception as e:
            kind = failure_kind(task)
            log.error('job failed', id=task.id, kind=kind, error=str(e)[:500])
            task.state = 'failed'
            if not self.stopping.is_set() and not task.gone.is_set():
                try:
                    self.client.json('POST', f'/api/jobs/{task.id}/fail', {'error': scrub(str(e)), 'kind': kind})
                except (urllib.error.URLError, OSError, RuntimeError):
                    pass
        finally:
            with self.lock:
                self.tasks.pop(task.id, None)

    def train(self, task: Task, inputs: dict[str, Path], sim: Path, runs: Path, dir: Path):
        task.ran = self.flags(task.spec)
        with open(dir / 'train.log', 'wb') as out:
            env = job_env(OMP_NUM_THREADS=str(self.threads), PYTHONUNBUFFERED='1')
            task.proc = subprocess.Popen(self.command(task.spec, inputs, sim), cwd=sim,
                                         stdout=out, stderr=subprocess.STDOUT, env=env)
            while task.proc.poll() is None:
                task.run = task.run or next(runs.glob(f'*-{jobs.run_name(task.spec)}'), None)
                time.sleep(2)
        if self.stopping.is_set() or task.gone.is_set():
            return
        task.run = next(runs.glob(f'*-{jobs.run_name(task.spec)}'), None)
        if task.proc.returncode != 0 or not task.run or not (task.run / 'evals.json').exists():
            raise Refused(f'training exited {task.proc.returncode}:\n' + tail(dir / 'train.log'))

    def score(self, task: Task, inputs: dict[str, Path], sim: Path, runs: Path, dir: Path):
        """The brain played by terrarium.games: its table in report.txt, every game's numbers in games.json, and
        score.json with how long it took on what, so machines can be compared on the same job."""
        spec = task.spec
        task.run = runs / f'{time.strftime("%Y%m%d-%H%M%S")}-{jobs.run_name(spec)}'
        task.run.mkdir(parents=True)
        started = time.time()
        with open(task.run / 'report.txt', 'wb') as out, open(dir / 'score.log', 'wb') as err:
            env = job_env(OMP_NUM_THREADS='1', PYTHONUNBUFFERED='1', TERRARIUM_LOG='WARN')
            cmd = self.scorer(spec, inputs, sim, Path(os.path.relpath(task.run / 'games.json', sim)))
            task.proc = subprocess.Popen(cmd, cwd=sim, stdout=out, stderr=err, env=env)
            task.proc.wait()
        if self.stopping.is_set() or task.gone.is_set():
            return
        if task.proc.returncode != 0 or not (task.run / 'games.json').exists():
            raise Refused(f'scoring exited {task.proc.returncode}:\n' + tail(dir / 'score.log'))
        box = {k: self.specs.get(k) for k in ('os', 'cpu', 'cores')} | {'instance': self.instance}
        # games run one process per player and role, up to the cores this worker gives a job
        record = {'game': spec['score']['game'], 'seed': spec['seed'], 'episodes': spec['score']['episodes'],
                  'seconds': round(time.time() - started - task.paused, 1), 'paused': round(task.paused),
                  'cores_given': self.whole, 'machine': box}
        (task.run / 'score.json').write_text(json.dumps(record, indent=1) + '\n')

    def prepare(self, task: Task, dir: Path) -> dict[str, Path]:
        spec = task.spec
        jobs.check(spec)
        if not jobs.verify(spec, task.sig, self.signers):
            raise Refused('signature does not verify against allowed_signers')
        if spec['trusted'] and not self.trusted:
            raise Refused('a trusted job sent to a worker without --trusted')
        parent = spec['parent'] or {}
        if 'blob' in parent and task.parent != parent['blob']:
            raise Refused('the parent sent is not the one the job names')
        inputs = {'world': (spec['world'], spec['world_file'])}
        if not scoring(spec):
            inputs['train'] = (spec['train'], spec['train_file'])
        if task.parent:
            inputs['parent'] = (task.parent, parent.get('file', 'parent.pt'))
        paths = {}
        for kind, (digest, name) in inputs.items():
            path = dir / 'inputs' / kind / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.blob(digest))
            paths[kind] = path
        return paths

    def blob(self, digest: str) -> bytes:
        status, data = self.client.call('GET', f'/api/blobs/{digest}')
        if status != 200:
            raise Refused(f'blob {digest[:12]}: {status}')
        if sha256(data) != digest:
            raise Refused(f'blob {digest[:12]} does not match its sha256')
        return data

    def code(self, spec: dict) -> Path:
        """A checkout of the job's code with its packages synced, built once per commit (and overlay)."""
        key = code_key(spec)
        c = spec['code']
        dest, ready = self.home / 'code' / key, self.home / 'code' / f'{key}.ready'
        with self.lock:
            building = self.building.setdefault(key, threading.Lock())
        with building:
            if ready.exists():
                ready.touch()
                return dest
            if dest.exists():
                snapshot.remove(dest)
            if self.trusted and c['bundle']:
                snapshot.from_bundle(dest, self.blob(c['bundle']), c['commit'], c['overlay'] and self.blob(c['overlay']))
            else:
                if c['overlay']:
                    raise Refused('uncommitted code is only for --trusted workers')
                snapshot.from_public(dest, self.home / 'mirror.git', self.repo, c['commit'])
            check_lock(dest / 'sim' / 'uv.lock')
            sync(dest / 'sim')
            ready.touch()
            self.prune_code(keep=key)
            return dest

    def prune_code(self, keep: str):
        """Past commits' checkouts beyond the newest KEEP_CODE used, never one a job is using."""
        busy = {code_key(t.spec) for t in list(self.tasks.values())} | {keep}
        done = sorted((r for r in (self.home / 'code').glob('*.ready')), key=lambda r: r.stat().st_mtime, reverse=True)
        for ready in done[KEEP_CODE:]:
            key = ready.name.removesuffix('.ready')
            if key not in busy:
                ready.unlink()
                snapshot.remove(self.home / 'code' / key)
                log.info('old checkout removed', code=key)

    def train_command(self, spec: dict, inputs: dict[str, Path], sim: Path) -> list[str]:
        # the checkout's own python, not uv run: stopping it then stops training, and not just uv
        cmd = [str(python(sim)), '-m', 'terrarium.train', jobs.run_name(spec),
               '--world', str(inputs['world']), '--train', str(inputs['train']), '--seed', str(spec['seed']),
               '--workers', str(self.rollouts)]
        if 'parent' in inputs:
            cmd += ['--parent', str(inputs['parent'])]
        if spec['code']['overlay']:
            cmd.append('--scratch')
        asked, ran = {k: bool(spec.get(k)) for k in jobs.TRAINING}, self.flags(spec)
        cuda = bool(self.specs.get('gpus'))
        for key, on in asked.items():
            if on and not ran[key] and (key != 'fast' or not cuda):
                log.info(f'{key} dropped: {"no CUDA GPU" if key == "fast" else "no GPU"} on this machine', job=spec['name'])
        if spec.get('fast', True) and cuda and not ran['fast']:
            log.warn('fast dropped: triton is not installed, so torch.compile cannot build kernels here', job=spec['name'])
        cmd += [f'--{k.replace("_", "-")}' for k, on in ran.items() if on]
        return cap(cmd, self.slots, self.rules)

    def flags(self, spec: dict) -> dict[str, bool]:
        """fast and gpu_collect as they'll run: fast (compiled, bf16) is for CUDA, and on by default there, since it
        cut the update a quarter without moving the curve (`fast = false` turns it off); a brain stepped on the CPU is
        what a collect already does, so gpu_collect needs a GPU, an Apple one included."""
        cuda = bool(self.specs.get('gpus'))
        # torch.compile on CUDA needs triton, which Windows wheels don't have: inductor dies at the first compile
        return {'fast': bool(spec.get('fast', True)) and cuda and has_triton(),
                'gpu_collect': bool(spec.get('gpu_collect')) and (cuda or bool(self.specs.get('mps')))}

    def score_command(self, spec: dict, inputs: dict[str, Path], sim: Path, out: Path) -> list[str]:
        # on the CPU, one thread a process: the same games on any machine
        s = spec['score']
        cmd = [str(python(sim)), '-m', 'terrarium.games', s['game'], '--config', str(inputs['world']),
               '--baseline', *s['baselines'], '--brain', str(inputs['parent']), '--episodes', str(s['episodes']),
               '--seed', str(spec['seed']), '--processes', str(self.whole), '--out', str(out)]
        if s.get('wiped'):
            cmd.append('--wiped')
        if s.get('wiped_every'):
            cmd += ['--wiped-every', str(s['wiped_every'])]
        if s.get('wiped_on_event'):
            cmd.append('--wiped-on-event')
        return cap(cmd, 1, self.rules)

    def upload(self, task: Task, data: bytes):
        wait = 5
        while not task.gone.is_set() and not self.stopping.is_set():
            try:
                status, body = self.client.call('PUT', f'/api/jobs/{task.id}/result', data)
            except (urllib.error.URLError, OSError) as e:
                status, body = 0, str(e).encode()
            if status == 200:
                task.uploaded = True
                log.info('job uploaded', id=task.id, bytes=len(data))
                return
            if status in (400, 410, 413):
                raise Refused(f'upload refused: {status} {body[:200]!r}')
            log.warn('upload failed, trying again', id=task.id, status=status, wait=wait)
            time.sleep(wait)
            wait = min(wait * 2, 300)

    def state(self) -> tuple[str, str]:
        if self.paused:
            return 'paused', 'paused from the status page'
        if self.draining:
            return 'draining', 'finishing its jobs, then stopping'
        if self.tasks:
            return 'working', self.verdict.reason
        return ('waiting', self.verdict.reason) if self.verdict.action != 'go' else ('ready', self.verdict.reason)

    def status(self) -> dict:
        state, reason = self.state()
        seen = self.watch.seen
        return {'state': state, 'reason': reason, 'paused': self.paused, 'draining': self.draining,
                'slots': self.slots, 'trusted': self.trusted, 'rollouts': self.rollouts, 'threads': self.threads,
                'rules': vars(self.rules), 'machine': seen._asdict() if seen else None,
                'jobs': [t.summary() | {'usage': t.usage()} for t in self.tasks.values()]}


def tail(path: Path, lines: int = 40) -> str:
    return '\n'.join(path.read_text(errors='replace').splitlines()[-lines:]) if path.exists() else ''


def peek(run: Path, limit: int = jobs.PEEK_LIMIT) -> bytes:
    """The run so far as a tar.gz: run.json, metrics and its newest checkpoint, with the ones nearest a quarter and
    half the way while they fit. A checkpoint written in the last few seconds may be half written, so it waits."""
    checkpoints = [c for c in sorted((run / 'checkpoints').glob('*.pt')) if time.time() - c.stat().st_mtime > 10]
    if not checkpoints:
        raise ValueError('no checkpoint yet')
    newest = checkpoints[-1]
    near = {min(checkpoints, key=lambda c: abs(int(c.stem) - share * int(newest.stem))) for share in (0.25, 0.5)}
    for files in (sorted(near | {newest}), [newest]):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for name in ('run.json', 'metrics.jsonl'):
                if (run / name).exists():
                    tar.add(run / name, arcname=f'{run.name}/{name}')
            for c in files:
                tar.add(c, arcname=f'{run.name}/checkpoints/{c.name}')
        if len(buf.getvalue()) <= limit:
            return buf.getvalue()
    raise ValueError(f'over {limit} bytes with one checkpoint')


def pack(run: Path, instance: int | None = None, paused: float = 0, limit: int = jobs.RESULT_LIMIT,
         lent: bool = False) -> bytes:
    """The run folder as a tar.gz, without the replays serve caches. A rented machine's id goes into
    run.json so compute can tell its runs from another pod's with the same GPU, and the time the job
    sat paused so it isn't counted as training. Past the coordinator's limit every other checkpoint is
    left out until it fits, counting back from the last, which always goes (it's the brain); the run
    kept here has them all, and the run.json sent says how many were left out."""
    if instance is not None or paused or lent:
        record = json.loads((run / 'run.json').read_text())
        if instance is not None:
            record.setdefault('machine', {})['instance'] = instance
        if paused:
            record['paused'] = round(paused)
        if lent:
            for key in ('started', 'finished'):
                if key in record:
                    record[key] = utc(record[key])
        (run / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    checkpoints = sorted((run / 'checkpoints').glob('*.pt'))
    keep = set(checkpoints)
    while True:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            left_out = {f'{run.name}/checkpoints/{c.name}' for c in checkpoints if c not in keep}
            tar.add(run, arcname=run.name, filter=lambda m: None if '/replays' in m.name or m.name in left_out or
                    (left_out and m.name == f'{run.name}/run.json') else m)
            if left_out:
                record = json.loads((run / 'run.json').read_text()) | {'checkpoints_left_out': len(left_out)}
                body = (json.dumps(record, indent=2) + '\n').encode()
                info = tarfile.TarInfo(f'{run.name}/run.json')
                info.size, info.mtime = len(body), int((run / 'run.json').stat().st_mtime)
                tar.addfile(info, io.BytesIO(body))
        if len(buf.getvalue()) <= limit or len(keep) <= 1:
            if left_out:
                log.info('checkpoints left out to fit the result', run=run.name, kept=len(keep), of=len(checkpoints))
            return buf.getvalue()
        keep = set([c for c in checkpoints if c in keep][::-1][::2])


def prune(runs: Path, gb: float):
    """Oldest runs first, until what's left fits in gb."""
    def size(run: Path) -> int:
        return sum(f.stat().st_size for f in run.rglob('*') if f.is_file())
    kept = sorted((r for r in runs.iterdir() if r.is_dir()), key=lambda r: r.name)
    sizes = {r: size(r) for r in kept}
    while kept and sum(sizes[r] for r in kept) > gb * 2**30:
        shutil.rmtree(kept.pop(0))


# the status page's pause/resume/drain need this header, which a web page can't send to another site without asking
# first (CORS preflight, which this server never answers), so a site you visit can't flip your worker
LOCAL = 'X-Terrarium-Worker'


def status_server(worker: Worker, port: int) -> ThreadingHTTPServer:
    hosts: set[str] = set()

    class Handler(BaseHTTPRequestHandler):
        def local(self) -> bool:
            # a name some website points at 127.0.0.1 (DNS rebinding) arrives with that name as its Host
            return self.headers.get('Host') in hosts

        def do_GET(self):
            if not self.local():
                return self.reply(None, 403)
            self.reply(worker.status() if self.path == '/status' else None)

        def do_POST(self):
            if not self.local() or self.headers.get(LOCAL) != '1':
                return self.reply(None, 403)
            match self.path:
                case '/pause':
                    worker.paused = True
                case '/resume':
                    worker.paused = worker.draining = False
                case '/drain':
                    worker.draining = True
                case _:
                    return self.reply(None)
            log.info('worker set', paused=worker.paused, draining=worker.draining)
            self.reply(worker.status())

        def reply(self, body, status: int = 404):
            data = json.dumps(body if body is not None else {'error': 'not found' if status == 404 else 'not allowed'}).encode()
            self.send_response(200 if body is not None else status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    bound = server.server_address[1]
    hosts.update({f'127.0.0.1:{bound}', f'localhost:{bound}'})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_calibration(args, rules: machine.Rules):
    # a worker with a job running here would be measured along with the runs
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/status', timeout=3) as r:
            if json.loads(r.read()).get('jobs'):
                sys.exit('a worker on this machine is running a job: pause and drain it (or stop it) first')
    except (OSError, ValueError):
        pass
    sim = Path(__file__).resolve().parent.parent
    py = python(sim)
    if subprocess.run([str(py), '-c', 'import torch'], capture_output=True).returncode:
        print('installing torch for the calibration runs...', flush=True)
        sync(sim)
    args.home.mkdir(parents=True, exist_ok=True)
    # a calibration only counts for a worker run at the same cpu share, which a bare `calibrate` easily misses
    print(f'cpu share {rules.cpu:g}: `worker run` needs the same (--anytime, --cpu or settings.toml) to use this', flush=True)
    # the runs start in sim/, so a path given here is made absolute from where this was run
    chosen = {'world': args.world and str(Path(args.world).resolve()), 'train': args.train and str(Path(args.train).resolve()),
              'memory': args.memory}
    record = calibrate.run(args.home, sim, py, rules, specs(), lambda n: shares(n, rules, args.rollouts),
                           lambda cmd, n: cap(cmd, n, rules), VERSION, **{k: v for k, v in chosen.items() if v is not None})
    print(f'{record["slots"]} slot{"s" if record["slots"] > 1 else ""}: {record["why"]}')
    print(f'saved to {args.home / calibrate.FILE}; `worker run` uses it unless --slots is given')


def origin() -> str:
    return snapshot.git('remote', 'get-url', 'origin', check=False)


STOPS = [signal.SIGTERM, signal.SIGINT, *([signal.SIGBREAK] if sys.platform == 'win32' else [])]


def interrupt(signum, frame):
    # uv run passes its own SIGTERM on, so a second one can land while the first is handing jobs back
    for sig in STOPS:
        signal.signal(sig, signal.SIG_IGN)
    raise KeyboardInterrupt


def token(path: Path) -> str:
    """The token file, asking for it the first time."""
    if not path.exists() and sys.stdin.isatty():
        import getpass
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(getpass.getpass('token (from River): ').strip() + '\n')
        path.chmod(0o600)
    return jobs.token(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='run', choices=['run', 'pause', 'resume', 'drain', 'status', 'calibrate'])
    parser.add_argument('--server', default=jobs.SERVER)
    parser.add_argument('--home', type=Path, default=HOME)
    parser.add_argument('--token-file', type=Path, help='default: HOME/token')
    parser.add_argument('--slots', type=int, help='jobs at once, the cores split between them (default: what `calibrate` '
                        'found for this machine, else 1)')
    parser.add_argument('--world', help='calibrate: the world to train in (default: %s)' % calibrate.WORLD)
    parser.add_argument('--train', help='calibrate: the training config (default: %s)' % calibrate.TRAIN)
    parser.add_argument('--memory', type=int, help='calibrate: notes of memory to give the fresh brain (default: %d)' % calibrate.MEMORY)
    parser.add_argument('--rollouts', type=int, help='rollout processes per job (default: its share of cores, up to 8)')
    parser.add_argument('--trusted', action='store_true', help='also run uncommitted code (only on your own machines)')
    parser.add_argument('--paused', action='store_true', help='start without taking jobs; resume from the status page')
    parser.add_argument('--max-load', type=float, help="don't take a job while the 1-minute load is above this")
    parser.add_argument('--instance', type=int, help='the rented machine id, written into each run.json; '
                        'implies --anytime')
    parser.add_argument('--anytime', action='store_true', help='none of the rules below: for machines nobody uses')
    rules = parser.add_argument_group('keeping out of the way (also settable in HOME/settings.toml)')
    rules.add_argument('--cooldown', type=float, help='minutes without keyboard or mouse before training '
                       '(default 10; 0 trains while in use too)')
    rules.add_argument('--battery', action='store_const', const=True, help='train on battery too')
    rules.add_argument('--battery-floor', type=float, help='with --battery, pause at or below this %% charge until '
                       'plugged in (default 30; 0 for no floor)')
    rules.add_argument('--cpu', type=float, help='share of the cores (default 0.5)')
    rules.add_argument('--gpu-temp', type=float, help='pause above this many °C (default 85; 0 for no limit)')
    rules.add_argument('--share-gpu', action='store_const', const=True,
                       help='keep training while other programs use the GPU')
    parser.add_argument('--repo', default=origin(), help='where public code is fetched from (default: origin)')
    parser.add_argument('--signers', type=Path, default=jobs.SIGNERS, help='keys jobs must be signed with')
    parser.add_argument('--trust-new-signers', action='store_true',
                        help='allowed_signers changed since the first run, and you have checked the change')
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    if args.command not in ('run', 'calibrate'):
        method = 'GET' if args.command == 'status' else 'POST'
        req = urllib.request.Request(f'http://127.0.0.1:{args.port}/{args.command}', method=method, headers={LOCAL: '1'},
                                     data=b'' if method == 'POST' else None)
        with urllib.request.urlopen(req, timeout=10) as r:
            print(json.dumps(json.loads(r.read()), indent=1))
        return
    if args.anytime or args.instance is not None:
        rules = machine.Rules.anytime()
    else:
        rules = machine.load(args.home / 'settings.toml', cooldown=args.cooldown, battery=args.battery,
                             battery_floor=args.battery_floor, cpu=args.cpu, gpu_temp=args.gpu_temp,
                             share_gpu=args.share_gpu)
    if args.command == 'calibrate':
        return run_calibration(args, rules)
    if why := jobs.can_verify(args.signers):
        sys.exit(f'{why}\nSee "Running a worker" in docs/compute.md.')
    if why := pin_signers(args.signers, args.home, args.trust_new_signers):
        sys.exit(why)
    machine.limit(rules)
    client = jobs.Client(args.server, token(args.token_file or args.home / 'token'))
    slots, why, fresh = calibrate.choose(args.slots, args.home, calibrate.identity(specs(), rules.cpu), VERSION)
    (log.info if fresh else log.warn)('slots', n=slots, why=why)
    worker = Worker(client, args.home, slots, args.trusted, args.paused, args.rollouts, args.max_load,
                    args.instance, args.repo, args.signers, rules=rules)
    # systemd and pods stop with SIGTERM, Windows consoles with Ctrl-Break; a background job may have
    # inherited SIGINT ignored
    for sig in STOPS:
        signal.signal(sig, interrupt)
    status_server(worker, args.port)
    log.info('status page', url=f'http://127.0.0.1:{args.port}/status')
    try:
        worker.loop()
    except KeyboardInterrupt:
        log.info('stopping: handing jobs back')
        worker.stop()


if __name__ == '__main__':
    main()
