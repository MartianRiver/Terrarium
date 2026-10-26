# The job queue's server: holds jobs and blobs (store.py) and hands them to
# workers. It trusts nothing it relays: jobs come signed from River's machine
# and workers check that themselves. What it does decide is who gets what:
#
#   admin    adds jobs and blobs, lists, cancels, retries, fetches results
#   trusted  River's own machines: any job, including uncommitted code
#   rented   machines River rents (Vast pods): the same jobs as trusted, and
#            the ones kept to rented machines (on = "rented")
#   donor    someone else's machine: only jobs on public code, and only the
#            blobs of the job it holds right now
#
# /api/health and /api/board (what each machine has done, board.py) need no token.
#
#   uv run python -m terrarium.coordinator serve --root DIR [--port 5192]
#   uv run python -m terrarium.coordinator token NAME --role donor --root DIR   (prints the token once)
#   uv run python -m terrarium.coordinator revoke NAME --root DIR

import argparse
import json
import secrets
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import board, jobs
from .log import Logger
from .store import Full, Gone, Store, sha256, write_atomic

log = Logger('coordinator')

PORT = 5194
ROLES = ('admin', *jobs.MACHINES)
LIMITS = {'blob': 16_000_000, 'result': 8_000_000, 'json': 64_000}
# requests a minute per machine token, and how many it may make at once; a worker makes a few a minute
RATE, BURST = 60, 60
# seconds between writes of workers.json when nothing but the time last seen has changed
SAVE_EVERY = 60


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Tokens:
    def __init__(self, root: Path):
        self.path = Path(root) / 'tokens.json'

    def load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def who(self, token: str) -> dict | None:
        # only hashes are kept, so a copy of the state folder doesn't hand out tokens
        return self.load().get(sha256(token.encode())) if token else None

    def add(self, name: str, role: str) -> str:
        if role not in ROLES or not jobs.NAME.match(name):
            raise ValueError(f'bad name or role: {name!r} {role!r}')
        tokens = self.load()
        if any(t['name'] == name for t in tokens.values()):
            raise ValueError(f'{name} already has a token; revoke it first')
        token = secrets.token_urlsafe(32)
        tokens[sha256(token.encode())] = {'name': name, 'role': role}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path, (json.dumps(tokens, indent=1) + '\n').encode())
        self.path.chmod(0o600)
        return token

    def revoke(self, name: str):
        tokens = {k: v for k, v in self.load().items() if v['name'] != name}
        write_atomic(self.path, (json.dumps(tokens, indent=1) + '\n').encode())


class Bucket:
    """Requests per token: a token that floods the coordinator gets 429s, not the others' share."""

    def __init__(self, rate: float = RATE, burst: float = BURST):
        self.rate, self.burst = rate / 60, burst
        self.left: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def take(self, name: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self.lock:
            left, then = self.left.get(name, (self.burst, now))
            left = min(self.burst, left + (now - then) * self.rate)
            self.left[name] = (left - 1 if left >= 1 else left, now)
            return left >= 1


class Queue:
    def __init__(self, root: Path, signers: Path | None = jobs.SIGNERS):
        self.store, self.tokens = Store(root), Tokens(root)
        self.signers = signers if signers and signers.exists() and shutil.which('ssh-keygen') else None
        # what each worker last said about itself, kept so the board outlives a restart
        self.seen_path = Path(root) / 'workers.json'
        self.workers: dict[str, dict] = json.loads(self.seen_path.read_text()) if self.seen_path.exists() else {}
        self.saved = 0.0
        self.lock = threading.Lock()
        self.bucket = Bucket()

    def seen(self, who: dict, info: dict | None = None):
        with self.lock:
            entry = self.workers.setdefault(who['name'], {'role': who['role']})
            entry['role'], entry['seen'] = who['role'], time.time()
            changed = False
            if info:
                kept = board.clean(info)
                changed, entry['info'] = kept != entry.get('info'), kept
            if changed or entry['seen'] - self.saved > SAVE_EVERY:
                write_atomic(self.seen_path, (json.dumps(self.workers, indent=1) + '\n').encode())
                self.saved = entry['seen']

    def board(self) -> dict:
        roles = {t['name']: t['role'] for t in self.tokens.load().values()}
        with self.lock:
            workers = json.loads(json.dumps(self.workers))
        return board.summary(self.store.all(), workers, roles)

    def add(self, body: dict):
        spec, sig = body.get('spec'), body.get('sig')
        try:
            jobs.check(spec)  # type: ignore[arg-type]
        except jobs.BadJob as e:
            raise Refused(400, str(e))
        if not isinstance(sig, str) or (self.signers and not jobs.verify(spec, sig, self.signers)):  # type: ignore[arg-type]
            raise Refused(403, 'signature does not verify')
        try:
            self.store.add(spec, sig)  # type: ignore[arg-type]
        except (ValueError, KeyError) as e:
            raise Refused(400, str(e))

    def list(self) -> list[dict]:
        with self.store.lock:
            self.store.expire(time.time())
        return [j | {'blocked': self.store.blocked(j), 'sig': None} for j in self.store.all()]

    def claim(self, who: dict) -> dict | None:
        job = self.store.claim(who['name'], trusted=who['role'] != 'donor', role=who['role'])
        if job is None:
            return None
        return {'spec': job['spec'], 'sig': job['sig'], 'parent': self.store.parent_blob(job)}

    def may_read(self, who: dict, digest: str) -> bool:
        if who['role'] != 'donor':
            return True
        for job in self.store.all():
            if job['state'] == 'running' and job['worker'] == who['name']:
                spec = job['spec']
                if digest in (spec['world'], spec['train'], self.store.parent_blob(job)):
                    return True
        return False


def handler(queue: Queue):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'terrarium-jobs'

        def do_GET(self):
            self.route('GET')

        def do_HEAD(self):
            self.route('HEAD')

        def do_POST(self):
            self.route('POST')

        def do_PUT(self):
            self.route('PUT')

        def route(self, method: str):
            parts = self.path.split('?')[0].strip('/').split('/')
            try:
                if parts == ['api', 'health']:
                    return self.json({'ok': True})
                if parts == ['api', 'board'] and method == 'GET':
                    # public, and read by the site from its own origin
                    return self.json(queue.board(), cors=True)
                who = queue.tokens.who(self.headers.get('Authorization', '').removeprefix('Bearer '))
                if who is None:
                    raise Refused(401, 'no such token')
                if who['role'] != 'admin' and not queue.bucket.take(who['name']):
                    raise Refused(429, f'over {RATE} requests a minute')
                self.dispatch(method, parts, who)
            except Refused as e:
                self.json({'error': str(e)}, e.status)
            except Gone as e:
                self.json({'error': f'job {e} is not yours any more'}, 410)
            except KeyError as e:
                self.json({'error': f'no such thing: {e}'}, 404)
            except Full as e:
                self.json({'error': str(e)}, 507)
            except Exception as e:
                log.error('request failed', path=self.path, error=repr(e), exc=True)
                self.json({'error': 'something broke on the coordinator'}, 500)

        def dispatch(self, method: str, parts: list[str], who: dict):
            admin, worker = who['role'] == 'admin', who['role'] in ROLES
            match method, parts:
                case ('GET' | 'HEAD'), ['api', 'blobs', digest] if worker:
                    if not queue.may_read(who, digest):
                        raise Refused(403, 'not a blob of a job you hold')
                    self.send(queue.store.get(digest), 'application/octet-stream', head=method == 'HEAD')
                case 'PUT', ['api', 'blobs', digest] if admin:
                    data = self.body('blob')
                    if sha256(data) != digest:
                        raise Refused(400, 'body does not match its sha256')
                    queue.store.put(data)
                    self.json({'ok': True})
                case 'POST', ['api', 'jobs'] if admin:
                    queue.add(json.loads(self.body('json')))
                    self.json({'ok': True})
                case 'GET', ['api', 'jobs'] if admin:
                    self.json(queue.list())
                case 'GET', ['api', 'workers'] if admin:
                    self.json(queue.workers)
                case 'POST', ['api', 'jobs', id, ('cancel' | 'retry') as what] if admin:
                    getattr(queue.store, what)(id)
                    self.json({'ok': True})
                case 'GET', ['api', 'results', id] if admin:
                    job = queue.store.read(id)
                    if not job['result']:
                        raise Refused(409, 'not done')
                    self.send(queue.store.get(job['result']), 'application/gzip')
                case 'POST', ['api', 'hello'] if worker:
                    # one worker per token, so a worker saying hello has just started
                    queue.seen(who, json.loads(self.body('json') or b'{}'))
                    self.json({'returned': queue.store.restarted(who['name'])})
                case 'POST', ['api', 'status'] if worker:
                    # a worker's minute-by-minute report, sent whether it's working or not
                    queue.seen(who, json.loads(self.body('json') or b'{}'))
                    self.json({'ok': True})
                case 'POST', ['api', 'claim'] if worker:
                    info = json.loads(self.body('json') or b'{}')
                    queue.seen(who, info)
                    job = queue.claim(who)
                    self.json(job) if job else self.send(b'', 'text/plain', 204)
                case 'POST', ['api', 'jobs', id, 'beat'] if worker:
                    progress = json.loads(self.body('json') or b'{}').get('progress')
                    queue.seen(who)
                    queue.store.beat(id, who['name'], progress if isinstance(progress, dict) else None)
                    self.json({'ok': True})
                case 'PUT', ['api', 'jobs', id, 'result'] if worker:
                    try:
                        queue.store.finish(id, who['name'], self.body('result'))
                    except (ValueError, OSError) as e:
                        raise Refused(400, f'not a finished run: {e}')
                    self.json({'ok': True})
                case 'POST', ['api', 'jobs', id, 'return'] if worker:
                    queue.store.give_back(id, who['name'])
                    self.json({'ok': True})
                case 'POST', ['api', 'jobs', id, 'fail'] if worker:
                    error = json.loads(self.body('json') or b'{}').get('error', '')
                    queue.store.fail(id, who['name'], str(error))
                    self.json({'ok': True})
                case _:
                    raise Refused(404, f'nothing at {method} {self.path} for a {who["role"]} token')

        def body(self, kind: str) -> bytes:
            length = self.headers.get('Content-Length')
            if length is None or not length.isdigit():
                raise Refused(411, 'needs a Content-Length')
            # refused before reading, so an oversized upload never sits in memory
            if int(length) > LIMITS[kind]:
                raise Refused(413, f'over {LIMITS[kind]} bytes')
            return self.rfile.read(int(length))

        def json(self, body, status: int = 200, cors: bool = False):
            self.send(json.dumps(body).encode(), 'application/json', status, cors=cors)

        def send(self, body: bytes, kind: str, status: int = 200, head: bool = False, cors: bool = False):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            if cors:
                self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def log_message(self, format, *args):
            log.debug('request', line=format % args)

    return Handler


def serve(root: Path, port: int = PORT, host: str = '127.0.0.1', signers: Path | None = jobs.SIGNERS) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(Queue(root, signers)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True, help='where jobs, blobs and tokens are kept')
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('serve')
    s.add_argument('--port', type=int, default=PORT)
    s.add_argument('--host', default='127.0.0.1')
    s.add_argument('--signers', type=Path, default=jobs.SIGNERS, help='refuse jobs not signed by these keys')
    t = sub.add_parser('token')
    t.add_argument('name')
    t.add_argument('--role', choices=ROLES, required=True)
    sub.add_parser('revoke').add_argument('name')
    args = parser.parse_args()
    match args.command:
        case 'serve':
            server = serve(args.root, args.port, args.host, args.signers)
            checked = Queue(args.root, args.signers).signers
            log.info('serving jobs', root=str(args.root), url=f'http://{args.host}:{args.port}/api/health',
                     signatures='checked' if checked else 'not checked (no ssh-keygen or signers file)')
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        case 'token':
            print(Tokens(args.root).add(args.name, args.role))
        case 'revoke':
            Tokens(args.root).revoke(args.name)


if __name__ == '__main__':
    main()
