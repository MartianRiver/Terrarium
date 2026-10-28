# A local window on training for the viewer's runs page: every run in runs/,
# its metrics, checkpoints and evals, and a replay of any checkpoint. Replays
# are recorded the first time they're asked for (a couple of seconds each) in
# the run's own world, and kept in the run's replays/ folder.
#
#   uv run python -m terrarium.serve [--port 5190]
#
#   GET /api/runs
#   GET /api/runs/<id>  (with what went into its brain, per machine)
#   GET /api/compute    (every run and rental so far, per machine)
#   GET /api/runs/<id>/replay/<checkpoint.pt | random>?seed=0[&here]  (here: recorded again on this machine)
#   GET /api/runs/<id>/mind/<checkpoint.pt>?seed=0&creature=ID  (one Terrikin's mind through that episode, mind.py)
#   GET /api/runs/<id>/wiring/<checkpoint.pt>  (its strongest connections, for drawing it wired up)
#   POST /api/play {run, checkpoint, seed}  (a game as one Terrikin among a brain's, play.py; all optional: by default
#                                           the newest checkpoint of the newest live run)
#   POST /api/play/<game> {ticks, thrust, turn, yes}  (the next few ticks, with what you're doing in them)
#
# Given a built viewer's folder (watch.py does), it serves the viewer's pages beside the API too.

import argparse
import json
import math
import mimetypes
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import compute
from .config import Config, build, upgrade
from .log import Logger
from .brain import load as load_brain
from .mind import track, wiring
from .play import Games
from .record import record
from .runs import ROOT

log = Logger('serve')

PORT = 5190
# the evals at the end of a run take under half a minute with no metrics written
STALE = 120
SECONDS = 180
NAME = re.compile(r'^[\w.-]+$')
# what a built viewer is made of; Windows takes types from the registry otherwise, and a .js as text/plain won't run
KINDS = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
         '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.gz': 'application/gzip'}


class NotFound(LookupError):
    pass


def state(run: Path, rec: dict) -> str:
    if 'finished' in rec:
        return 'finished'
    newest = max(p.stat().st_mtime for p in (run / 'run.json', run / 'metrics.jsonl') if p.exists())
    return 'live' if time.time() - newest < STALE else 'stopped'


def checkpoints(run: Path) -> list[dict]:
    return [{'file': p.name, 'samples': int(p.stem)} for p in sorted((run / 'checkpoints').glob('*.pt'))]


def summary(run: Path, rentals: list[dict]) -> dict:
    rec = compute.read_run(run)
    rows = compute.metrics(run)
    return {'id': rec['id'], 'started': rec['started'], 'finished': rec.get('finished'), 'state': state(run, rec),
            'scratch': rec['scratch'], 'world': rec['world']['file'], 'device': rec.get('device'),
            'gpu': rec.get('gpu'), 'hardware': compute.hardware(rec, rentals), 'samples': rows[-1]['samples'] if rows else 0,
            'target': rec['train']['config']['ppo']['samples'], 'seconds': compute.seconds(run),
            'evals': rec.get('evals')}


class Runs:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.recording = threading.Lock()

    def find(self, id: str) -> Path:
        run = self.root / id
        if not NAME.match(id) or not (run / 'run.json').exists():
            raise NotFound(f'no run {id}')
        return run

    def dirs(self) -> list[Path]:
        return [p for p in self.root.iterdir() if (p / 'run.json').exists()] if self.root.exists() else []

    def list(self) -> list[dict]:
        rentals = compute.sessions()
        runs = [summary(p, rentals) for p in self.dirs()]
        # newest first, by start time: a pod names its runs in UTC
        return sorted(runs, key=lambda r: compute.when(r['started']), reverse=True)

    def detail(self, id: str) -> dict:
        run = self.find(id)
        rec = compute.read_run(run)
        evals = run / 'evals.json'
        return {'run': rec, 'state': state(run, rec), 'metrics': compute.metrics(run), 'checkpoints': checkpoints(run),
                'evals': json.loads(evals.read_text()) if evals.exists() else None,
                'compute': compute.behind(run.parent, run)}

    def replay(self, id: str, checkpoint: str, seed: int, here: bool = False) -> Path:
        """random is generation 0: how a brain trained from scratch starts out. here records it again on this
        machine, for a mind to match: one recorded on a pod can part from what this machine plays."""
        run = self.find(id)
        if checkpoint != 'random' and checkpoint not in {c['file'] for c in checkpoints(run)}:
            raise NotFound(f'{id} has no checkpoint {checkpoint}')
        out = run / 'replays' / f'{Path(checkpoint).stem}-{seed}{"-here" if here else ""}.jsonl.gz'
        with self.recording:
            if not out.exists():
                cfg = build(Config, upgrade(compute.read_run(run)['world']['config']))
                out.parent.mkdir(exist_ok=True)
                partial = out.with_name(out.name + '.part')
                brain = None if checkpoint == 'random' else run / 'checkpoints' / checkpoint
                record(cfg, partial, round(SECONDS * cfg.tick_hz), seed, brain=brain)
                partial.rename(out)
        return out

    def game(self, id: str | None = None, checkpoint: str | None = None) -> tuple[Config, Path, str]:
        """A run's world and one of its checkpoints to play against: by default the newest checkpoint of the newest
        live run (or of the newest run, if none is live)."""
        if id is None:
            listed = self.list()
            pool = [r for r in listed if r['state'] == 'live'] or listed
            id = next((r['id'] for r in pool if checkpoints(self.find(r['id']))), None)
            if id is None:
                raise NotFound('no run with a checkpoint to play against yet')
        run = self.find(id)
        files = [c['file'] for c in checkpoints(run)]
        checkpoint = checkpoint or (files[-1] if files else '')
        if checkpoint not in files:
            raise NotFound(f'{id} has no checkpoint {checkpoint}')
        cfg = build(Config, upgrade(compute.read_run(run)['world']['config']))
        return cfg, run / 'checkpoints' / checkpoint, f'{id}/{checkpoint}'

    def wiring(self, id: str, checkpoint: str) -> dict:
        """A checkpoint's strongest connections (mind.wiring)."""
        run = self.find(id)
        if checkpoint not in {c['file'] for c in checkpoints(run)}:
            raise NotFound(f'{id} has no checkpoint {checkpoint}')
        brain, _ = load_brain(run / 'checkpoints' / checkpoint)
        return wiring(brain)

    def mind(self, id: str, checkpoint: str, seed: int, creature: int) -> Path:
        """One Terrikin's mind through the episode of that replay (mind.py), recorded once."""
        run = self.find(id)
        if checkpoint not in {c['file'] for c in checkpoints(run)}:
            raise NotFound(f'{id} has no checkpoint {checkpoint}')
        out = run / 'replays' / f'{Path(checkpoint).stem}-{seed}.mind-{creature}.jsonl.gz'
        with self.recording:
            if not out.exists():
                cfg = build(Config, upgrade(compute.read_run(run)['world']['config']))
                out.parent.mkdir(exist_ok=True)
                partial = out.with_name(out.name + '.part')
                track(cfg, run / 'checkpoints' / checkpoint, partial, seed, creature)
                partial.rename(out)
        return out


def number(body: dict, key: str, low: float, high: float, default: float) -> float:
    value = body.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f'{key} must be a number')
    return min(max(float(value), low), high)


def handler(runs: Runs, static: Path | None = None):
    games = Games()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            parts = urlsplit(self.path).path.strip('/').split('/')
            try:
                size = int(self.headers.get('Content-Length') or 0)
                if size > 4096:
                    raise ValueError('too much to read')
                body = json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError('send a JSON object')
                match parts:
                    case ['api', 'play']:
                        id, checkpoint = body.get('run'), body.get('checkpoint')
                        if not all(v is None or isinstance(v, str) for v in (id, checkpoint)):
                            raise ValueError('run and checkpoint are names')
                        cfg, brain, label = runs.game(id, checkpoint)
                        seed = int(number(body, 'seed', 0, 2**31 - 1, secrets.randbelow(2**31)))
                        token, game = games.start(cfg, brain, seed, label)
                        self.json({'game': token, 'label': label, 'header': game.header, 'frame': game.first,
                                   'you': game.you, 'controls': game.controls, 'score': game.score()})
                    case ['api', 'play', token]:
                        game = games.get(token)
                        if game is None:
                            raise NotFound('that game is over (or this server restarted)')
                        yes = body.get('yes', [])
                        if not isinstance(yes, list) or len(yes) > 8 or not all(isinstance(y, str) for y in yes):
                            raise ValueError('yes is a list of action names')
                        frames = game.step(int(number(body, 'ticks', 1, 10, 1)), number(body, 'thrust', -1, 1, 0),
                                           number(body, 'turn', -1, 1, 0), yes)
                        self.json({'frames': frames, 'score': game.score()})
                    case _:
                        raise NotFound(f'nothing at {self.path}')
            except NotFound as e:
                self.json({'error': str(e)}, 404)
            except ValueError as e:
                self.json({'error': str(e)}, 400)
            except Exception as e:
                log.error('request failed', path=self.path, error=repr(e))
                self.json({'error': f'something broke: {e!r}'}, 500)

        def do_GET(self):
            url = urlsplit(self.path)
            parts = url.path.strip('/').split('/')
            try:
                if static and parts[0] != 'api':
                    return self.page(url.path)
                match parts:
                    case ['api', 'runs']:
                        self.json(runs.list())
                    case ['api', 'compute']:
                        self.json(compute.everything(runs.root))
                    case ['api', 'runs', id]:
                        self.json(runs.detail(id))
                    case ['api', 'runs', id, 'replay', checkpoint]:
                        query = parse_qs(url.query, keep_blank_values=True)
                        seed = int(query.get('seed', ['0'])[0])
                        self.send(runs.replay(id, checkpoint, seed, 'here' in query).read_bytes(), 'application/gzip')
                    case ['api', 'runs', id, 'wiring', checkpoint]:
                        self.json(runs.wiring(id, checkpoint))
                    case ['api', 'runs', id, 'mind', checkpoint]:
                        query = parse_qs(url.query)
                        seed, creature = (int(query.get(k, ['0'])[0]) for k in ('seed', 'creature'))
                        self.send(runs.mind(id, checkpoint, seed, creature).read_bytes(), 'application/gzip')
                    case _:
                        raise NotFound(f'nothing at {url.path}')
            except NotFound as e:
                self.json({'error': str(e)}, 404)
            except ValueError as e:
                # a bad seed, or a run whose world or brain today's code can't load
                self.json({'error': str(e)}, 400)
            except Exception as e:
                log.error('request failed', path=self.path, error=repr(e))
                self.json({'error': f'something broke: {e!r}'}, 500)

        def page(self, path: str):
            assert static
            file = (static / (path.strip('/') or 'index.html')).resolve()
            if not file.is_relative_to(static.resolve()) or not file.is_file():
                raise NotFound(f'nothing at {path}')
            kind = KINDS.get(file.suffix) or mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            self.send(file.read_bytes(), kind)

        def json(self, body, status: int = 200):
            self.send(json.dumps(body).encode(), 'application/json', status)

        def send(self, body: bytes, kind: str, status: int = 200):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            log.debug('request', line=format % args)

    return Handler


def serve(root: Path = ROOT, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(('127.0.0.1', port), handler(Runs(root)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    server = serve(port=args.port)
    log.info('serving runs', root=str(ROOT), url=f'http://127.0.0.1:{args.port}/api/runs')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
