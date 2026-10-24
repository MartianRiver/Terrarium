# A machine that trains for the queue: asks the coordinator for a job, checks
# it, builds the job's code, runs terrarium.train in it and uploads the run.
#
#   uv run python -m terrarium.worker --server URL [--slots 1] [--trusted] [--paused]
#   uv run python -m terrarium.worker pause | resume | drain | status
#
# Before a job runs, every one of these has to hold (docs/compute.md):
#   - its spec is signed by a key in sim/allowed_signers (this checkout's copy, not the server's)
#   - every input matches the sha256 the signed spec names
#   - without --trusted: the code is fetched from the public repo by this worker, and only run
#     if it's on main or next; bundles and overlays (uncommitted code) are refused
# The server can't send commands; all it can say is "this signed job, please".
#
# Everything lives in --home (~/.terrarium/worker): the token, a checkout per
# commit, each job's inputs and log. The status page and pause/resume listen
# on 127.0.0.1 only.

import argparse
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import jobs, runs, snapshot
from .log import Logger
from .store import sha256

log = Logger('worker')

HOME = jobs.HOME / 'worker'
PORT = 5191
POLL = 30
BEAT = 60
VERSION = 1


def cpus() -> int:
    # containers report the host's cores; the cgroup quota is what this one may use
    return runs.cpu_quota() or os.cpu_count() or 1


def torch_extra() -> list[str]:
    # on Linux torch only comes with an extra (pyproject.toml)
    if sys.platform != 'linux':
        return []
    return ['--extra', 'cuda' if shutil.which('nvidia-smi') else 'cpu']


def sync(sim: Path):
    subprocess.run(['uv', 'sync', '-q', '--locked', *torch_extra()], cwd=sim, check=True, capture_output=True)


class Refused(Exception):
    pass


class Task:
    def __init__(self, job: dict):
        self.spec, self.sig, self.parent = job['spec'], job['sig'], job.get('parent')
        self.id = self.spec['id']
        self.state = 'preparing'
        self.proc: subprocess.Popen | None = None
        self.run: Path | None = None
        self.gone = threading.Event()
        self.started = time.time()

    def progress(self) -> dict:
        p = {'state': self.state, 'samples': 0, 'samples_per_second': None}
        if self.run and (self.run / 'metrics.jsonl').exists():
            rows = (self.run / 'metrics.jsonl').read_text().splitlines()
            for line in reversed(rows):
                try:
                    row = json.loads(line)
                    p |= {'samples': row['samples'], 'samples_per_second': row['samples_per_second']}
                    break
                except (ValueError, KeyError):
                    continue
        return p

    def summary(self) -> dict:
        return {'id': self.id, 'name': self.spec['name'], 'batch': self.spec['batch'], 'total': self.spec['samples'],
                'since': self.started, **self.progress()}


class Worker:
    def __init__(self, client: jobs.Client, home: Path = HOME, slots: int = 1, trusted: bool = False,
                 paused: bool = False, rollouts: int | None = None, max_load: float | None = None,
                 instance: int | None = None, repo: str = '', signers: Path = jobs.SIGNERS, command=None):
        self.client, self.home, self.slots, self.trusted = client, Path(home), slots, trusted
        self.paused, self.draining, self.stopping = paused, False, threading.Event()
        share = max(1, cpus() // slots)
        self.threads, self.rollouts = share, rollouts or max(1, min(8, share - 1))
        self.max_load, self.instance, self.repo, self.signers = max_load, instance, repo, signers
        self.command = command or self.train_command
        self.tasks: dict[str, Task] = {}
        self.lock = threading.Lock()
        self.building: dict[str, threading.Lock] = {}
        for d in ('code', 'jobs'):
            (self.home / d).mkdir(parents=True, exist_ok=True)

    # the loop

    def loop(self):
        last_beat = 0.0
        log.info('worker started', slots=self.slots, trusted=self.trusted, paused=self.paused,
                 rollouts=self.rollouts, threads=self.threads, platform=platform.platform())
        self.hello()
        while not self.stopping.is_set():
            if time.time() - last_beat >= BEAT:
                self.beat()
                last_beat = time.time()
            if self.draining and not self.tasks:
                break
            if self.wants_work():
                try:
                    job = self.client.json('POST', '/api/claim', self.info())
                except (urllib.error.URLError, OSError, RuntimeError) as e:
                    log.warn('claim failed', error=str(e))
                    job = None
                if job:
                    self.start(job)
                    continue
            self.stopping.wait(POLL if not self.tasks else 5)

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
        if self.paused or self.draining or len(self.tasks) >= self.slots:
            return False
        if self.max_load is not None and hasattr(os, 'getloadavg') and os.getloadavg()[0] > self.max_load:
            log.debug('busy machine, not claiming', load=os.getloadavg()[0], max=self.max_load)
            return False
        return True

    def info(self) -> dict:
        return {'platform': platform.platform(), 'slots': self.slots, 'trusted': self.trusted, 'version': VERSION}

    def start(self, job: dict):
        task = Task(job)
        with self.lock:
            self.tasks[task.id] = task
        threading.Thread(target=self.work, args=(task,), name=f'job-{task.id}', daemon=True).start()

    def beat(self):
        for task in list(self.tasks.values()):
            try:
                self.client.json('POST', f'/api/jobs/{task.id}/beat', {'progress': task.progress()})
            except RuntimeError as e:
                if ' 410 ' in str(e):
                    log.warn('job taken away', id=task.id)
                    task.gone.set()
                    if task.proc and task.proc.poll() is None:
                        task.proc.terminate()
            except (urllib.error.URLError, OSError) as e:
                log.warn('beat failed', id=task.id, error=str(e))

    def stop(self):
        """Hand every unfinished job back and stop; a job given back doesn't count against it."""
        self.stopping.set()
        for task in list(self.tasks.values()):
            if task.proc and task.proc.poll() is None:
                task.proc.terminate()
            if task.state in ('preparing', 'training'):
                try:
                    self.client.json('POST', f'/api/jobs/{task.id}/return')
                except (urllib.error.URLError, OSError, RuntimeError) as e:
                    log.warn('could not give a job back; its lease will run out', id=task.id, error=str(e))

    # one job

    def work(self, task: Task):
        dir = self.home / 'jobs' / task.id
        try:
            inputs = self.prepare(task, dir)
            code = self.code(task.spec)
            task.state = 'training'
            log.info('training', id=task.id, name=task.spec['name'], code=code.name)
            # half a run from an attempt that was stopped would be mistaken for this one
            for old in (code / 'runs').glob(f'*-{jobs.run_name(task.spec)}'):
                shutil.rmtree(old)
            with open(dir / 'train.log', 'wb') as out:
                env = {k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'}
                env |= {'OMP_NUM_THREADS': str(self.threads), 'PYTHONUNBUFFERED': '1'}
                # relative, so the paths run.json records don't carry this machine's home folder
                rel = {k: Path(os.path.relpath(v, code / 'sim')) for k, v in inputs.items()}
                task.proc = subprocess.Popen(self.command(task.spec, rel), cwd=code / 'sim', stdout=out,
                                             stderr=subprocess.STDOUT, env=env)
                while task.proc.poll() is None:
                    task.run = task.run or next((code / 'runs').glob(f'*-{jobs.run_name(task.spec)}'), None)
                    time.sleep(2)
            if self.stopping.is_set() or task.gone.is_set():
                return
            task.run = next((code / 'runs').glob(f'*-{jobs.run_name(task.spec)}'), None)
            if task.proc.returncode != 0 or not task.run or not (task.run / 'evals.json').exists():
                raise Refused(f'training exited {task.proc.returncode}:\n' + tail(dir / 'train.log'))
            task.state = 'uploading'
            (task.run / 'job.json').write_text(json.dumps({'spec': task.spec, 'sig': task.sig}, indent=1) + '\n')
            if task.spec['code']['overlay']:
                # diff.patch has tracked changes and untracked.txt only names; this is the code itself
                (task.run / 'overlay.tar.gz').write_bytes(self.blob(task.spec['code']['overlay']))
            self.upload(task, pack(task.run, self.instance))
            shutil.rmtree(task.run)
            shutil.rmtree(dir / 'inputs', ignore_errors=True)
            task.state = 'done'
        except Exception as e:
            log.error('job failed', id=task.id, error=str(e)[:500])
            task.state = 'failed'
            if not self.stopping.is_set() and not task.gone.is_set():
                try:
                    self.client.json('POST', f'/api/jobs/{task.id}/fail', {'error': str(e)})
                except (urllib.error.URLError, OSError, RuntimeError):
                    pass
        finally:
            with self.lock:
                self.tasks.pop(task.id, None)

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
        inputs = {'world': (spec['world'], spec['world_file']), 'train': (spec['train'], spec['train_file'])}
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
        c = spec['code']
        key = c['commit'][:12] + (f'-{c["overlay"][:12]}' if c['overlay'] else '')
        dest, ready = self.home / 'code' / key, self.home / 'code' / f'{key}.ready'
        with self.lock:
            building = self.building.setdefault(key, threading.Lock())
        with building:
            if ready.exists():
                return dest
            if dest.exists():
                snapshot.remove(dest)
            if self.trusted and c['bundle']:
                snapshot.from_bundle(dest, self.blob(c['bundle']), c['commit'], c['overlay'] and self.blob(c['overlay']))
            else:
                if c['overlay']:
                    raise Refused('uncommitted code is only for --trusted workers')
                snapshot.from_public(dest, self.home / 'mirror.git', self.repo, c['commit'])
            sync(dest / 'sim')
            ready.touch()
            return dest

    def train_command(self, spec: dict, inputs: dict[str, Path]) -> list[str]:
        cmd = ['uv', 'run', '--frozen', *torch_extra(), 'python', '-m', 'terrarium.train', jobs.run_name(spec),
               '--world', str(inputs['world']), '--train', str(inputs['train']), '--seed', str(spec['seed']),
               '--workers', str(self.rollouts)]
        if 'parent' in inputs:
            cmd += ['--parent', str(inputs['parent'])]
        if spec['code']['overlay']:
            cmd.append('--scratch')
        return cmd

    def upload(self, task: Task, data: bytes):
        wait = 5
        while not task.gone.is_set() and not self.stopping.is_set():
            try:
                status, body = self.client.call('PUT', f'/api/jobs/{task.id}/result', data)
            except (urllib.error.URLError, OSError) as e:
                status, body = 0, str(e).encode()
            if status == 200:
                log.info('job uploaded', id=task.id, bytes=len(data))
                return
            if status in (400, 410, 413):
                raise Refused(f'upload refused: {status} {body[:200]!r}')
            log.warn('upload failed, trying again', id=task.id, status=status, wait=wait)
            time.sleep(wait)
            wait = min(wait * 2, 300)

    def status(self) -> dict:
        return {'paused': self.paused, 'draining': self.draining, 'slots': self.slots, 'trusted': self.trusted,
                'rollouts': self.rollouts, 'threads': self.threads, 'jobs': [t.summary() for t in self.tasks.values()]}


def tail(path: Path, lines: int = 40) -> str:
    return '\n'.join(path.read_text(errors='replace').splitlines()[-lines:]) if path.exists() else ''


def pack(run: Path, instance: int | None = None) -> bytes:
    """The run folder as a tar.gz, without the replays serve caches. A rented machine's id goes into
    run.json so compute can tell its runs from another pod's with the same GPU."""
    if instance is not None:
        record = json.loads((run / 'run.json').read_text())
        record.setdefault('machine', {})['instance'] = instance
        (run / 'run.json').write_text(json.dumps(record, indent=2) + '\n')
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        tar.add(run, arcname=run.name, filter=lambda m: None if '/replays' in m.name else m)
    return buf.getvalue()


def status_server(worker: Worker, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.reply(worker.status() if self.path == '/status' else None)

        def do_POST(self):
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

        def reply(self, body):
            data = json.dumps(body if body is not None else {'error': 'not found'}).encode()
            self.send_response(200 if body is not None else 404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def origin() -> str:
    return snapshot.git('remote', 'get-url', 'origin', check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='run', choices=['run', 'pause', 'resume', 'drain', 'status'])
    parser.add_argument('--server', default=jobs.SERVER)
    parser.add_argument('--home', type=Path, default=HOME)
    parser.add_argument('--token-file', type=Path, help='default: HOME/token')
    parser.add_argument('--slots', type=int, default=1, help='jobs at once; the cores are split between them')
    parser.add_argument('--rollouts', type=int, help='rollout processes per job (default: its share of cores, up to 8)')
    parser.add_argument('--trusted', action='store_true', help='also run uncommitted code (only on your own machines)')
    parser.add_argument('--paused', action='store_true', help='start without taking jobs; resume from the status page')
    parser.add_argument('--max-load', type=float, help="don't take a job while the 1-minute load is above this")
    parser.add_argument('--instance', type=int, help='the rented machine id, written into each run.json')
    parser.add_argument('--repo', default=origin(), help='where public code is fetched from (default: origin)')
    parser.add_argument('--signers', type=Path, default=jobs.SIGNERS, help='keys jobs must be signed with')
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    if args.command != 'run':
        client = jobs.Client(f'http://127.0.0.1:{args.port}', '')
        print(json.dumps(client.json('GET' if args.command == 'status' else 'POST', f'/{args.command}'), indent=1))
        return
    client = jobs.Client(args.server, jobs.token(args.token_file or args.home / 'token'))
    worker = Worker(client, args.home, args.slots, args.trusted, args.paused, args.rollouts, args.max_load,
                    args.instance, args.repo, args.signers)
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    # systemd and pods stop with SIGTERM; a background job may have inherited SIGINT ignored
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    status_server(worker, args.port)
    log.info('status page', url=f'http://127.0.0.1:{args.port}/status')
    try:
        worker.loop()
    except KeyboardInterrupt:
        log.info('stopping: handing jobs back')
        worker.stop()


if __name__ == '__main__':
    main()
