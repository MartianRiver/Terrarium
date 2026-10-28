# Training jobs: what one is, how it's signed, and the command line for adding
# a batch of them to a coordinator and bringing the finished runs home.
#
#   uv run python -m terrarium.jobs add grid.toml
#   uv run python -m terrarium.jobs list
#   uv run python -m terrarium.jobs cancel ID... | retry ID...
#   uv run python -m terrarium.jobs sync          finished runs → runs/
#
# A job is a JSON spec naming every input by sha256: the code (commit, bundle,
# overlay), world.toml, train.toml and the parent brain. It's signed here with
# an ssh key (ssh-keygen -Y sign) and every worker checks the signature against
# sim/allowed_signers before it touches anything, so the coordinator only
# relays: it can't make up a job or change one. See docs/compute.md.
#
# A batch file is TOML: top-level world/train/parent/seed apply to every
# [[job]], and each job can override them. Paths are relative to the batch file.
# parent is a .pt path, "run:<run id>/<checkpoint>" from runs/, or
# "job:<name>" for the final checkpoint of an earlier job in the same batch.
# on = "rented" (or "trusted", "donor") keeps a job to that kind of machine.
# chunk = N splits a job into pieces of N samples, each carrying on from the
# last, so a lent machine never holds more than a short job.

import argparse
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import snapshot
from .log import Logger
from .runs import ROOT
from .store import sha256

log = Logger('jobs')

FORMAT = 1
NAMESPACE = 'terrarium-job'
PRINCIPAL = 'terrarium'
SIGNERS = Path(__file__).resolve().parent.parent / 'allowed_signers'
HOME = Path.home() / '.terrarium'
KEY = Path.home() / '.ssh' / 'terrarium_jobs_ed25519'
SERVER = os.environ.get('TERRARIUM_JOBS', 'http://127.0.0.1:5194')
# the biggest result the coordinator takes; Atlas's nginx takes up to 17 MB
RESULT_LIMIT = 16_000_000
AGENT = 'terrarium-jobs/1'
NAME = re.compile(r'^[\w.-]{1,80}$')
DIGEST = re.compile(r'^[0-9a-f]{64}$')
FIELDS = {'world': str, 'train': str, 'parent': str, 'seed': int, 'on': str, 'chunk': int}
# the kinds of machine a job can be kept to; a token's role says which one a worker is
MACHINES = ('trusted', 'rented', 'donor')


class BadJob(ValueError):
    pass


# signing

# a fixed spec signed by the key in allowed_signers, so a worker can tell at start whether it can check jobs
CHECK = {'check': 'job signatures can be checked on this machine'}
CHECK_SIG = """-----BEGIN SSH SIGNATURE-----
U1NIU0lHAAAAAQAAADMAAAALc3NoLWVkMjU1MTkAAAAgESv0LuORjJnLlKgAclZ2tVCb8a
0k9AhUbRJ1z5CAUy0AAAANdGVycmFyaXVtLWpvYgAAAAAAAAAGc2hhNTEyAAAAUwAAAAtz
c2gtZWQyNTUxOQAAAEDxbr7OTySR0dbD6Xsb76ozm74K24lCa4q0cmP5v00orzX+w1FSoQ
+c8j8GuHbI2qkybOjq6dy3603hyhOFWnEL
-----END SSH SIGNATURE-----
"""


def keygen() -> str:
    # Windows 10's own OpenSSH may predate -Y (OpenSSH 8.1); Git for Windows brings a recent one
    if sys.platform == 'win32' and (git := shutil.which('git')):
        bundled = Path(git).resolve().parent.parent / 'usr' / 'bin' / 'ssh-keygen.exe'
        if bundled.exists():
            return str(bundled)
    return 'ssh-keygen'


def canonical(spec: dict) -> bytes:
    return json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()


def sign(spec: dict, key: Path = KEY) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / 'job.json'
        data.write_bytes(canonical(spec))
        subprocess.run([keygen(), '-q', '-Y', 'sign', '-f', str(key), '-n', NAMESPACE, str(data)],
                       check=True, capture_output=True)
        return (Path(tmp) / 'job.json.sig').read_text()


def checked(spec: dict, sig: str, signers: Path) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'job.sig'
        path.write_text(sig)
        return subprocess.run([keygen(), '-Y', 'verify', '-f', str(signers), '-I', PRINCIPAL, '-n', NAMESPACE,
                               '-s', str(path)], input=canonical(spec), capture_output=True)


def verify(spec: dict, sig: str, signers: Path = SIGNERS) -> bool:
    return checked(spec, sig, signers).returncode == 0


def can_verify(signers: Path = SIGNERS) -> str | None:
    """None if this machine checks a known good signature, else why not."""
    try:
        done = checked(CHECK, CHECK_SIG, signers)
    except OSError as e:
        return f'no ssh-keygen to check job signatures with ({e})'
    if done.returncode == 0:
        return None
    said = (done.stderr or done.stdout).decode(errors='replace').strip()[:300]
    return f'{keygen()} can\'t check job signatures against {signers}: {said}'


def check(spec: dict):
    """Refuse anything that isn't the shape add() makes, before a worker uses a single field of it."""
    def need(ok, what):
        if not ok:
            raise BadJob(f'job {spec.get("id")!r}: {what}')
    need(isinstance(spec, dict) and spec.get('format') == FORMAT, f'format is not {FORMAT}')
    need(isinstance(spec.get('id'), str) and re.fullmatch(r'[0-9a-f]{12}', spec['id']), 'bad id')
    for key in ('batch', 'name', 'world_file', 'train_file'):
        need(isinstance(spec.get(key), str) and NAME.match(spec[key]), f'bad {key}')
    for key in ('world', 'train'):
        need(isinstance(spec.get(key), str) and DIGEST.match(spec[key]), f'bad {key} digest')
    need(isinstance(spec.get('seed'), int) and isinstance(spec.get('samples'), int), 'bad seed or samples')
    need(isinstance(spec.get('trusted'), bool), 'bad trusted')
    code = spec.get('code') or {}
    need(isinstance(code, dict) and isinstance(code.get('commit'), str) and re.fullmatch(r'[0-9a-f]{40}', code['commit']),
         'bad commit')
    for key in ('bundle', 'overlay'):
        need(code.get(key) is None or (isinstance(code[key], str) and DIGEST.match(code[key])), f'bad {key}')
    need(spec['trusted'] or not code.get('overlay'), 'an overlay job must be trusted')
    need(spec.get('on') in (None, *MACHINES), 'bad on')
    need(not (spec['trusted'] and spec.get('on') == 'donor'), 'a trusted job can never run on a donor')
    parent = spec.get('parent')
    need(parent is None or (isinstance(parent, dict) and (
        (set(parent) == {'blob', 'file'} and DIGEST.match(parent['blob']) and NAME.match(parent['file'])) or
        (set(parent) == {'job'} and re.fullmatch(r'[0-9a-f]{12}', parent['job'])))), 'bad parent')


def run_name(spec: dict) -> str:
    return f'{spec["name"]}-{spec["id"]}'


# batches

def load_batch(path: Path) -> list[dict]:
    with open(path, 'rb') as f:
        raw = tomllib.load(f)
    jobs = raw.pop('job', None)
    defaults = take(raw, f'{path.name}')
    if not isinstance(jobs, list) or not jobs:
        raise BadJob(f'{path.name}: no [[job]] tables')
    out, names = [], set()
    for i, entry in enumerate(jobs):
        name = entry.pop('name', None)
        if not isinstance(name, str) or not NAME.match(name) or name in names:
            raise BadJob(f'{path.name}: job {i} needs a unique name of letters, digits, - _ .')
        names.add(name)
        job = {'name': name, 'parent': '', 'seed': 0} | defaults | take(entry, f'{path.name} job {name}')
        for key in ('world', 'train'):
            if key not in job:
                raise BadJob(f'{path.name} job {name}: no {key}')
        if job.get('on') not in (None, *MACHINES):
            raise BadJob(f'{path.name} job {name}: on is one of {", ".join(MACHINES)}')
        if job.get('chunk', 1) < 1:
            raise BadJob(f'{path.name} job {name}: chunk is a number of samples')
        out.append(job)
    return out


def take(table: dict, where: str) -> dict:
    for key, value in table.items():
        if key not in FIELDS:
            raise BadJob(f'{where}: unknown key {key!r}')
        if not isinstance(value, FIELDS[key]) or isinstance(value, bool):
            raise BadJob(f'{where}: {key} should be {FIELDS[key].__name__}')
    return dict(table)


def specs(path: Path, runs: Path = ROOT, repo: Path = snapshot.REPO) -> tuple[list[dict], dict[str, bytes]]:
    """A batch file as unsigned job specs, and the blobs they name."""
    path = Path(path)
    batch, blobs = path.stem, {}

    def blob(data: bytes) -> str:
        digest = sha256(data)
        blobs[digest] = data
        return digest

    commit = snapshot.commit(repo)
    extra = snapshot.overlay(repo)
    code = {'commit': commit, 'bundle': blob(snapshot.bundle(repo)), 'overlay': extra and blob(extra)}
    trusted = extra is not None or not snapshot.public(commit, repo)
    ids, out = {}, []
    for job in load_batch(path):
        world, train = path.parent / job['world'], path.parent / job['train']
        text = train.read_text()
        samples = tomllib.loads(text).get('ppo', {}).get('samples')
        if not isinstance(samples, int):
            raise BadJob(f'{train.name}: no [ppo] samples')
        chunk = job.get('chunk') or samples
        pieces = -(-samples // chunk)
        before = parent(job['parent'], path.parent, runs, ids, blob)
        for i in range(pieces):
            name = job['name'] if pieces == 1 else f'{job["name"]}.{i + 1}'
            if name in ids:
                raise BadJob(f'{path.name}: two jobs named {name}')
            size = min(chunk, samples - i * chunk)
            spec = {'format': FORMAT, 'id': secrets.token_hex(6), 'batch': batch, 'name': name,
                    'added': time.time() + len(out) * 1e-3, 'code': code, 'trusted': trusted,
                    'world': blob(world.read_bytes()), 'world_file': world.name,
                    'train': blob(train.read_bytes() if pieces == 1 else with_samples(text, size).encode()),
                    'train_file': train.name, 'parent': before,
                    # each piece plays its own episodes, not the first piece's again
                    'seed': job['seed'] + 1000 * i, 'samples': size, 'on': job.get('on')}
            ids[name] = spec['id']
            before = {'job': spec['id']}
            out.append(spec)
        # job:<name> means the last piece
        ids[job['name']] = out[-1]['id']
    return out, blobs


def with_samples(text: str, samples: int) -> str:
    """A train.toml with [ppo] samples changed, checked by reading it back."""
    section, lines = None, []
    for line in text.splitlines(keepends=True):
        if found := re.match(r'\s*\[([^\[\]]+)\]', line):
            section = found.group(1).strip()
        if section == 'ppo' and re.match(r'\s*samples\s*=', line):
            line = f'samples = {samples}\n'
        lines.append(line)
    out, want = ''.join(lines), tomllib.loads(text)
    want['ppo']['samples'] = samples
    if tomllib.loads(out) != want:
        raise BadJob(f"couldn't set [ppo] samples to {samples}")
    return out


def parent(text: str, here: Path, runs: Path, ids: dict, blob) -> dict | None:
    if not text:
        return None
    if text.startswith('job:'):
        if text[4:] not in ids:
            raise BadJob(f'parent {text}: no earlier job of that name in this batch')
        return {'job': ids[text[4:]]}
    if text.startswith('run:'):
        run, _, checkpoint = text[4:].partition('/')
        file = runs / run / 'checkpoints' / checkpoint
    else:
        file = here / text
    if not file.is_file():
        raise BadJob(f'parent {text}: no file at {file}')
    # sent byte for byte: the meta saved inside is how lineage finds the parent's run
    return {'blob': blob(file.read_bytes()), 'file': file.name}


# talking to a coordinator

class Client:
    def __init__(self, server: str, token: str, timeout: float = 60):
        self.server, self.token, self.timeout = server.rstrip('/'), token, timeout

    def call(self, method: str, path: str, body=None) -> tuple[int, bytes]:
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        kind = 'application/json' if not isinstance(body, bytes) else 'application/octet-stream'
        req = urllib.request.Request(self.server + path, data=data, method=method, headers={
            'Authorization': f'Bearer {self.token}', 'Content-Type': kind,
            # Cloudflare turns away Python's own User-Agent
            'User-Agent': AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def json(self, method: str, path: str, body=None) -> Any:
        status, data = self.call(method, path, body)
        if status >= 400:
            raise RuntimeError(f'{method} {path}: {status} {data[:300]!r}')
        return json.loads(data) if data else None


def token(path: Path) -> str:
    data = path.read_bytes()
    # Windows PowerShell's `echo x > file` writes UTF-16 with a byte-order mark
    return (data.decode('utf-16') if data[:2] in (b'\xff\xfe', b'\xfe\xff') else data.decode('utf-8-sig')).strip()


def add(client: Client, path: Path, key: Path = KEY, runs: Path = ROOT, repo: Path = snapshot.REPO) -> list[dict]:
    jobs, blobs = specs(path, runs, repo)
    for digest, data in blobs.items():
        if client.call('HEAD', f'/api/blobs/{digest}')[0] != 200:
            client.json('PUT', f'/api/blobs/{digest}', data)
    for spec in jobs:
        client.json('POST', '/api/jobs', {'spec': spec, 'sig': sign(spec, key)})
    log.info('batch added', batch=jobs[0]['batch'], jobs=len(jobs), trusted=jobs[0]['trusted'],
             commit=jobs[0]['code']['commit'][:7], overlay=bool(jobs[0]['code']['overlay']))
    return jobs


def sync(client: Client, runs: Path = ROOT) -> list[Path]:
    """Every done job's run, unpacked into runs/ unless it's there already."""
    got = []
    for job in client.json('GET', '/api/jobs'):
        spec = job['spec']
        if job['state'] != 'done' or any(runs.glob(f'*-{run_name(spec)}')):
            continue
        status, data = client.call('GET', f'/api/results/{spec["id"]}')
        if status != 200:
            log.warn('result not fetched', id=spec['id'], status=status)
            continue
        got.append(unpack(data, spec, runs))
    return got


def unpack(data: bytes, spec: dict, runs: Path) -> Path:
    # a donor's result is data from a stranger: one run folder of the right name, nothing outside it
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        tops = {m.name.split('/')[0] for m in tar.getmembers()}
        if len(tops) != 1 or not next(iter(tops)).endswith('-' + run_name(spec)) or not NAME.match(next(iter(tops))):
            raise BadJob(f'result for {spec["id"]} is not one run folder named for it: {sorted(tops)[:5]}')
        runs.mkdir(parents=True, exist_ok=True)
        tar.extractall(runs, filter='data')
    path = runs / next(iter(tops))
    log.info('run synced', id=spec['id'], run=path.name)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', default=SERVER)
    parser.add_argument('--token-file', type=Path, default=HOME / 'admin.token')
    parser.add_argument('--runs', type=Path, default=ROOT, help='where run: parents are found and runs are synced to')
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('add')
    a.add_argument('batch', type=Path)
    a.add_argument('--key', type=Path, default=KEY, help='the ssh key jobs are signed with')
    sub.add_parser('list')
    for name in ('cancel', 'retry'):
        sub.add_parser(name).add_argument('ids', nargs='+')
    sub.add_parser('sync')
    sub.add_parser('workers')
    args = parser.parse_args()
    client = Client(args.server, token(args.token_file))
    match args.command:
        case 'add':
            for spec in add(client, args.batch, args.key, args.runs):
                print(spec['id'], spec['name'])
        case 'list':
            for job in client.json('GET', '/api/jobs'):
                spec, p = job['spec'], job['progress'] or {}
                done = f'{p.get("samples", 0) / spec["samples"]:.0%}' if job['state'] == 'running' else ''
                on = f'on {spec["on"]}' if spec.get('on') else ''
                print(f'{spec["id"]}  {spec["batch"]:<16} {spec["name"]:<24} {job["state"]:<9} {done:>4}  '
                      f'{on:<10} {job["worker"] or ""}{"  blocked" if job.get("blocked") else ""}')
        case 'cancel' | 'retry':
            for id in args.ids:
                client.json('POST', f'/api/jobs/{id}/{args.command}')
        case 'sync':
            for path in sync(client, args.runs):
                print(path.name)
        case 'workers':
            for name, w in client.json('GET', '/api/workers').items():
                info = w.get('info') or {}
                specs = info.get('specs') or {}
                gpus = ', '.join(f'{g["name"]} {g["memory_gb"]} GB' for g in specs.get('gpus') or [])
                ago = time.time() - w.get('seen', 0)
                print(f'{name:<16} {w["role"]:<8} {info.get("state", "?"):<9} {ago / 60:>5.1f} min ago  '
                      f'{specs.get("os") or info.get("platform", "")}; {specs.get("cpu")}, {specs.get("cores")} cores, '
                      f'{specs.get("memory_gb")} GB; {gpus or "no NVIDIA GPU"}  {info.get("reason") or ""}')


if __name__ == '__main__':
    main()
