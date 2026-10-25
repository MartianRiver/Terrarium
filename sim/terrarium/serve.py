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
#   GET /api/runs/<id>/replay/<checkpoint.pt | random>?seed=0

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import compute
from .config import Config, build, upgrade
from .log import Logger
from .record import record
from .runs import ROOT

log = Logger('serve')

PORT = 5190
# the evals at the end of a run take under half a minute with no metrics written
STALE = 120
SECONDS = 180
NAME = re.compile(r'^[\w.-]+$')


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

    def list(self) -> list[dict]:
        rentals = compute.sessions()
        runs = [summary(p, rentals) for p in self.root.iterdir() if (p / 'run.json').exists()] if self.root.exists() else []
        # newest first, by start time: a pod names its runs in UTC
        return sorted(runs, key=lambda r: compute.when(r['started']), reverse=True)

    def detail(self, id: str) -> dict:
        run = self.find(id)
        rec = compute.read_run(run)
        evals = run / 'evals.json'
        return {'run': rec, 'state': state(run, rec), 'metrics': compute.metrics(run), 'checkpoints': checkpoints(run),
                'evals': json.loads(evals.read_text()) if evals.exists() else None,
                'compute': compute.behind(self.root, run)}

    def replay(self, id: str, checkpoint: str, seed: int) -> Path:
        """random is generation 0: how a brain trained from scratch starts out."""
        run = self.find(id)
        if checkpoint != 'random' and checkpoint not in {c['file'] for c in checkpoints(run)}:
            raise NotFound(f'{id} has no checkpoint {checkpoint}')
        out = run / 'replays' / f'{Path(checkpoint).stem}-{seed}.jsonl.gz'
        with self.recording:
            if not out.exists():
                cfg = build(Config, upgrade(compute.read_run(run)['world']['config']))
                out.parent.mkdir(exist_ok=True)
                partial = out.with_name(out.name + '.part')
                brain = None if checkpoint == 'random' else run / 'checkpoints' / checkpoint
                record(cfg, partial, round(SECONDS * cfg.tick_hz), seed, brain=brain)
                partial.rename(out)
        return out


def handler(runs: Runs):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            parts = url.path.strip('/').split('/')
            try:
                match parts:
                    case ['api', 'runs']:
                        self.json(runs.list())
                    case ['api', 'compute']:
                        self.json(compute.everything(runs.root))
                    case ['api', 'runs', id]:
                        self.json(runs.detail(id))
                    case ['api', 'runs', id, 'replay', checkpoint]:
                        seed = int(parse_qs(url.query).get('seed', ['0'])[0])
                        self.send(runs.replay(id, checkpoint, seed).read_bytes(), 'application/gzip')
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
