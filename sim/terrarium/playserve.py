# The hosted play server for friends with an invite (invites.py): only the play routes of serve.py, against the newest
# checkpoint of the newest run under --runs, with a cap on games at once and on each invite's. Nothing is kept: a
# restart ends every game. The viewer is served beside it as static files; this answers /api/play only.
#   PLAY_INVITE_KEY=… python -m terrarium.playserve --runs DIR [--port 5197] [--games 6] [--each 2] [--name 'the 0.3 brain']

import argparse
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import torch

from . import invites
from .log import Logger
from .play import Game, Games
from .serve import NotFound, Runs, number, opened, step

log = Logger('playserve')

PORT = 5197
IDLE = 120  # seconds without a step before a game is dropped
PACE = 2.0  # a game runs at most this many times faster than its world's clock


class Full(Exception):
    pass


class Hosted(Games):
    """Games for invited friends: full means no new game until one ends (no one is pushed out mid-game), and each
    invite can hold only so many, its oldest dropped for a new one (a page reloaded shouldn't lock a friend out)."""

    def __init__(self, total: int, each: int):
        super().__init__()
        self.total, self.each = total, each
        self.owner: dict[str, str] = {}
        self.due: dict[str, float] = {}

    def begin(self, cfg, brain: Path, seed: int, label: str, who: str) -> tuple[str, Game]:
        with self.lock:
            self._drop([t for t, g in self.games.items() if time.time() - g.used > IDLE])
            mine = sorted((t for t, o in self.owner.items() if o == who), key=lambda t: self.games[t].used)
            self._drop(mine[:max(0, len(mine) - self.each + 1)])
            if len(self.games) >= self.total:
                raise Full('every seat is taken: try again in a few minutes')
        game = Game(cfg, brain, seed, label)
        token = secrets.token_urlsafe(12)
        with self.lock:
            self.games[token], self.owner[token], self.due[token] = game, who, 0.0
        log.info('game started', who=who, games=len(self.games))
        return token, game

    def wait(self, token: str, ticks: int, hz: float):
        """Hold a reply back so a game can't be stepped faster than PACE times real time."""
        now = time.monotonic()
        with self.lock:
            due = self.due.get(token, 0.0)
            self.due[token] = max(now, due) + ticks / hz / PACE
        if due > now:
            time.sleep(due - now)

    def _drop(self, tokens):
        for t in tokens:
            self.games.pop(t, None)
            self.owner.pop(t, None)
            self.due.pop(t, None)


def handler(runs: Runs, games: Hosted, key: str, name: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

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
                        code = body.get('invite')
                        if not isinstance(code, str):
                            raise invites.BadInvite('playing here needs an invite')
                        who = invites.check(key, code)
                        cfg, brain, label = runs.game()
                        label = name or label
                        token, game = games.begin(cfg, brain, secrets.randbelow(2**31), label, who)
                        self.json(opened(token, game, label))
                    case ['api', 'play', token]:
                        game = games.get(token)
                        if game is None:
                            raise NotFound('that game is over (or this server restarted)')
                        games.wait(token, int(number(body, 'ticks', 1, 10, 1)), game.hz)
                        self.json(step(game, body))
                    case _:
                        raise NotFound(f'nothing at {self.path}')
            except invites.BadInvite as e:
                self.json({'error': str(e)}, 403)
            except Full as e:
                self.json({'error': str(e)}, 503)
            except NotFound as e:
                self.json({'error': str(e)}, 404)
            except ValueError as e:
                self.json({'error': str(e)}, 400)
            except Exception as e:
                log.error('request failed', path=self.path, error=repr(e))
                self.json({'error': 'something broke on the server'}, 500)

        def do_GET(self):
            if urlsplit(self.path).path == '/api/play':
                self.json({'games': len(games.games), 'seats': games.total})
            else:
                self.json({'error': f'nothing at {self.path}'}, 404)

        def json(self, body, status: int = 200):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(root: Path, key: str, port: int = PORT, total: int = 6, each: int = 2, name: str | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(('127.0.0.1', port), handler(Runs(root), Hosted(total, each), key, name))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runs', type=Path, required=True, help='a folder of runs; the newest one with a checkpoint is played')
    p.add_argument('--port', type=int, default=PORT)
    p.add_argument('--games', type=int, default=6, help='games at once')
    p.add_argument('--each', type=int, default=2, help='games at once for one invite')
    p.add_argument('--name', help='what the viewer calls the brain (the run and checkpoint otherwise)')
    args = p.parse_args()
    key = os.environ.get('PLAY_INVITE_KEY')
    if not key:
        raise SystemExit('PLAY_INVITE_KEY isn’t set')
    # every game steps its brain on one thread; a container that shows the host's cores would oversubscribe
    torch.set_num_threads(1)
    server = serve(args.runs, key, args.port, args.games, args.each, args.name)
    _, _, label = Runs(args.runs).game()
    log.info('serving play', brain=label, url=f'http://127.0.0.1:{args.port}/api/play', games=args.games)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
