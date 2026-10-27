# Saves what harness.js POSTs: /frame/<clip>/<n> as OUT/frames/<clip>/<n>.jpg, /card/<name> as OUT/cards/<name>.png.
# python3 reel/receive.py OUT   (127.0.0.1:8799; keep OUT outside the repo)
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

out = Path(sys.argv[1])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        parts = self.path.strip('/').split('/')
        if parts[0] == 'card' and len(parts) == 2:
            path = out / 'cards' / f'{parts[1]}.png'
        elif parts[0] == 'frame' and len(parts) == 3:
            path = out / 'frames' / parts[1] / f'{int(parts[2]):05d}.jpg'
        else:
            self.send_response(404)
            self.cors()
            self.end_headers()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.send_response(200)
        self.cors()
        self.end_headers()


ThreadingHTTPServer(('127.0.0.1', 8799), Handler).serve_forever()
