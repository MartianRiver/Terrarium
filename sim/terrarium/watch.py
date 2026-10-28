# Watch what this machine is training for the queue: the run a worker has going in one of its checkouts, and the
# ones it kept, played in the viewer as they train. The viewer's ?latest plays the newest checkpoint of each live
# run and looks again whenever the replay runs out, so a fast GPU's checkpoints in between are skipped.
#
# Each replay is recorded by the code of the job that trained it (its checkout, with that checkout's own packages),
# so a run made on another branch still plays in the world it was trained in. The viewer's files come from the site,
# checked against the sha256 each one is listed with, and the last good copy is used when the site can't be reached.
#
#   uv run python -m terrarium.watch [--home DIR] [--port 5196] [--viewer DIR] [--no-open]

import argparse
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from . import worker
from .log import Logger
from .serve import NAME, NotFound, Runs, checkpoints, handler

log = Logger('watch')

PORT = 5196
SITE = 'https://terrarium.martianriver.com/at-home/viewer/'
AGENT = f'terrarium-watch/{worker.VERSION}'


class Kept(Runs):
    """A worker's runs: those training in its checkouts (code/<key>/runs/) and those it kept (runs/)."""

    def __init__(self, home: Path):
        super().__init__(home / 'runs')
        self.home = home

    def dirs(self) -> list[Path]:
        found = [*self.home.glob('code/*/runs/*'), *self.root.glob('*')]
        return [p for p in found if (p / 'run.json').exists()]

    def find(self, id: str) -> Path:
        if NAME.match(id):
            for run in self.dirs():
                if run.name == id:
                    return run
        raise NotFound(f'no run {id}')

    def code(self, run: Path) -> Path | None:
        """The checkout that trained a run: the one it's training in, or for a kept one, the one its job names."""
        if run.parent.parent.parent == self.home / 'code':
            return run.parent.parent
        job = run / 'job.json'
        if not job.exists():
            return None
        code = self.home / 'code' / worker.code_key(json.loads(job.read_text())['spec'])
        return code if (code / 'sim').is_dir() else None

    def replay(self, id: str, checkpoint: str, seed: int, here: bool = False) -> Path:
        run = self.find(id)
        code = self.code(run)
        if code is None or checkpoint == 'random':
            return super().replay(id, checkpoint, seed, here)
        if checkpoint not in {c['file'] for c in checkpoints(run)}:
            raise NotFound(f'{id} has no checkpoint {checkpoint}')
        out = run / 'replays' / f'{Path(checkpoint).stem}-{seed}.jsonl.gz'
        sim = code / 'sim'
        script = ('import sys; from pathlib import Path; from terrarium.serve import Runs; '
                  'Runs(Path(sys.argv[1])).replay(sys.argv[2], sys.argv[3], int(sys.argv[4]))')
        with self.recording:
            if not out.exists():
                done = subprocess.run([str(worker.python(sim)), '-c', script, str(run.parent), id, checkpoint, str(seed)],
                                      cwd=sim, capture_output=True, text=True, timeout=600)
                if done.returncode != 0 or not out.exists():
                    raise RuntimeError(f'recording in {code.name} failed: {done.stderr[-500:]}')
        return out


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': AGENT}), timeout=30) as r:
        return r.read()


def viewer(home: Path, site: str = SITE) -> Path | None:
    """The viewer's files in home/viewer, brought up to date from the site; None if there are none yet and the site
    can't be reached."""
    dest = home / 'viewer'
    try:
        files: dict[str, str] = json.loads(fetch(site + 'files.json'))['files']
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        log.warn('viewer not checked', site=site, error=str(e))
        return dest if (dest / 'index.html').exists() else None
    for name, digest in files.items():
        parts = PurePosixPath(name).parts
        if not parts or name.startswith('/') or any(p in ('..', '.') or not NAME.match(p) for p in parts):
            raise ValueError(f'the viewer lists a file it can\'t have: {name!r}')
        path = dest.joinpath(*parts)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        data = fetch(site + quote(name))
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'{name} from the site does not match its sha256')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for old in [p for p in dest.rglob('*') if p.is_file() and p.relative_to(dest).as_posix() not in files]:
        old.unlink()
    log.info('viewer ready', files=len(files))
    return dest


def main():
    parser = argparse.ArgumentParser(description='watch the runs this machine trains for the queue')
    parser.add_argument('--home', type=Path, default=worker.HOME, help='the worker\'s folder')
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--viewer', type=Path, help='a viewer built here (viewer/dist) instead of the site\'s')
    parser.add_argument('--no-open', action='store_true', help='don\'t open a browser')
    args = parser.parse_args()
    pages = args.viewer or viewer(args.home)
    if pages is None:
        raise SystemExit('no viewer yet, and the site can\'t be reached to get one')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(Kept(args.home), pages))
    url = f'http://127.0.0.1:{args.port}/?latest&follow'
    log.info('watching', home=str(args.home), url=url)
    print(f'Watching at {url} (the runs page: http://127.0.0.1:{args.port}/runs.html). Ctrl+C stops it.')
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
