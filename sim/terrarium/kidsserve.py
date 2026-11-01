# Catch them! on one machine (kids.py): serves the built viewer's kids page and plays its games against one tag
# brain, keeping every game in --keep (a replay each, and plays.jsonl). Made for a spare machine at home, so it
# listens on this machine only and plays one game at a time: a new one ends the last.
#   python -m terrarium.kidsserve --brain BRAIN.pt --keep DIR [--viewer viewer/dist] [--port 5195] [--open]
#
#   GET  /api/kids                   the modes' levels, and the last plays from plays.jsonl
#   POST /api/kids {mode, level, device}    a new game (level from 1)
#   POST /api/kids/<game> {ticks, thrust, turn, yes}   the next few ticks
#   POST /api/kids/<game>/end {why}  the page closed or went back to the start (sent as a beacon, any content type)

import argparse
import dataclasses
import json
import mimetypes
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import torch

from .kids import MODES, Catch
from .log import Logger
from .serve import KINDS, NotFound, number

log = Logger('kidsserve')

PORT = 5195
IDLE = 1800  # seconds without a step before a game counts as walked away from (a paused one waits this long)
VIEWER = Path(__file__).resolve().parents[2] / 'viewer' / 'dist'
WHY = {'quit', 'home', 'again'}


class Games:
    def __init__(self, brain: Path, keep: Path):
        self.brain, self.keep = brain, keep
        self.games: dict[str, Catch] = {}
        self.lock = threading.Lock()

    def start(self, mode: str, level: int, device: str) -> tuple[str, Catch]:
        game = Catch(mode, self.brain, secrets.randbelow(2**31), self.keep, device, level)
        token = secrets.token_urlsafe(12)
        with self.lock:
            for old in self.games.values():
                old.close('again')
            self.games = {token: game}
        log.info('game started', mode=mode, level=level, device=device)
        return token, game

    def get(self, token: str) -> Catch:
        with self.lock:
            for t, g in list(self.games.items()):
                if time.time() - g.used > IDLE:
                    g.close('idle')
                    del self.games[t]
            game = self.games.get(token)
        if game is None:
            raise NotFound('that game is over')
        return game

    def plays(self, last: int = 20) -> list[dict]:
        file = self.keep / 'plays.jsonl'
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text().splitlines()[-last:]]

    def stop(self):
        with self.lock:
            for g in self.games.values():
                g.close('stopped')


def handler(games: Games, static: Path):
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
                    case ['api', 'kids']:
                        mode, device = body.get('mode'), body.get('device', '')
                        if mode not in MODES:
                            raise ValueError(f'mode is one of {", ".join(MODES)}')
                        if not isinstance(device, str) or len(device) > 20:
                            raise ValueError('device is a short name')
                        level = int(number(body, 'level', 1, len(MODES[mode]), 1))
                        token, game = games.start(mode, level, device)
                        self.json({'game': token, 'header': game.header, 'frame': game.first, 'you': game.you,
                                   'controls': game.controls, 'score': game.score()})
                    case ['api', 'kids', token]:
                        game = games.get(token)
                        yes = body.get('yes', [])
                        if not isinstance(yes, list) or not all(isinstance(y, str) for y in yes[:8]):
                            raise ValueError('yes is a list of action names')
                        frames = game.step(int(number(body, 'ticks', 1, 10, 1)), number(body, 'thrust', -1, 1, 0),
                                           number(body, 'turn', -1, 1, 0), yes[:8])
                        self.json({'frames': frames, 'score': game.score(), 'events': game.events})
                    case ['api', 'kids', token, 'end']:
                        why = body.get('why')
                        games.get(token).close(why if why in WHY else 'quit')
                        self.json({'ok': True})
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
            path = urlsplit(self.path).path
            try:
                if path == '/api/kids':
                    modes = {k: [dataclasses.asdict(m) for m in levels] for k, levels in MODES.items()}
                    return self.json({'modes': modes, 'plays': games.plays()})
                file = (static / (path.strip('/') or 'kids.html')).resolve()
                if not file.is_relative_to(static.resolve()) or not file.is_file():
                    raise NotFound(f'nothing at {path}')
                kind = KINDS.get(file.suffix) or mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                self.send(file.read_bytes(), kind)
            except NotFound as e:
                self.json({'error': str(e)}, 404)

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


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--brain', type=Path, required=True, help='the tag brain the runners play (a checkpoint)')
    p.add_argument('--keep', type=Path, required=True, help='where every game is kept')
    p.add_argument('--viewer', type=Path, default=VIEWER, help='the built viewer (npm run build)')
    p.add_argument('--port', type=int, default=PORT)
    p.add_argument('--open', action='store_true', help='open the game in the browser')
    p.add_argument('--lite', action='store_true', help='lighter graphics, for a slow graphics chip')
    args = p.parse_args()
    if not (args.viewer / 'kids.html').exists():
        raise SystemExit(f'no kids.html in {args.viewer}: build the viewer first (npm run build in viewer/)')
    keep = args.keep.expanduser()
    keep.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    games = Games(args.brain, keep)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(games, args.viewer))
    url = f'http://127.0.0.1:{args.port}/{"?lite" if args.lite else ""}'
    log.info('serving the kids game', url=url, keep=str(keep))
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        games.stop()


if __name__ == '__main__':
    main()
