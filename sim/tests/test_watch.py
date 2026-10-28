import base64
import functools
import gzip
import hashlib
import json
import threading
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from terrarium import replay, watch
from terrarium.serve import NotFound, handler
from terrarium.worker import code_key

from test_serve import make_run

SIM = Path(__file__).resolve().parent.parent
SPEC = {'code': {'commit': 'a' * 40, 'overlay': 'b' * 64}}


def checkout(home: Path, key: str) -> Path:
    """A checkout in the worker's code/, its sim/ this one (packages and all)."""
    code = home / 'code' / key
    code.mkdir(parents=True)
    (code / 'sim').symlink_to(SIM)
    return code


def test_runs_training_in_a_checkout_and_kept_ones_are_both_found(tmp_path):
    code = checkout(tmp_path, code_key(SPEC))
    make_run(code / 'runs', 'training', '2026-10-28T12:00:00+1100', rows=[{'samples': 200, 'seconds': 1}])
    kept = make_run(tmp_path / 'runs', 'kept', '2026-10-28T10:00:00+1100', '2026-10-28T11:00:00+1100')
    (kept / 'job.json').write_text(json.dumps({'spec': SPEC}))
    runs = watch.Kept(tmp_path)
    assert [(r['id'], r['state']) for r in runs.list()] == [('training', 'live'), ('kept', 'finished')]
    assert runs.code(runs.find('training')) == code and runs.code(kept) == code
    with pytest.raises(NotFound):
        runs.find('..')


def test_a_replay_is_recorded_by_the_checkout_that_trained_it(tmp_path, monkeypatch):
    code = checkout(tmp_path, code_key(SPEC))
    make_run(code / 'runs', 'training', '2026-10-28T12:00:00+1100', checkpoints=[32768])
    runs = watch.Kept(tmp_path)
    path = runs.replay('training', '00000032768.pt', 2)
    head, frames = replay.read(path)
    assert path.parent == code / 'runs' / 'training' / 'replays'
    assert head['source']['seed'] == 2 and len(frames) > 1
    # once recorded, it isn't again
    monkeypatch.setattr(watch.subprocess, 'run', lambda *a, **k: pytest.fail('recorded twice'))
    assert runs.replay('training', '00000032768.pt', 2) == path
    with pytest.raises(NotFound):
        runs.replay('training', '00000065536.pt', 2)


def test_a_kept_run_whose_checkout_is_gone_plays_in_this_code(tmp_path):
    kept = make_run(tmp_path / 'runs', 'kept', '2026-10-28T10:00:00+1100', '2026-10-28T11:00:00+1100', checkpoints=[32768])
    (kept / 'job.json').write_text(json.dumps({'spec': SPEC}))
    runs = watch.Kept(tmp_path)
    assert runs.code(kept) is None
    assert runs.replay('kept', '00000032768.pt', 0).exists()


def site(folder: Path):
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(SimpleHTTPRequestHandler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}/'


def listed(folder: Path, files: dict[str, bytes], wrong: str = '', bundle_sha: str = ''):
    """What site.mjs publishes: the files, their bundle, and files.json with the sha256 of each and of the bundle."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    digests = {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}
    if wrong:
        digests[wrong] = '0' * 64
    bundle = gzip.compress(json.dumps({'files': {n: base64.b64encode(d).decode() for n, d in files.items()}}).encode())
    (folder / 'bundle.json.gz').write_bytes(bundle)
    (folder / 'files.json').write_text(json.dumps({'files': digests, 'bundle': bundle_sha or hashlib.sha256(bundle).hexdigest()}))


def test_the_viewer_comes_from_the_site_checked_and_kept_for_when_its_away(tmp_path):
    online = tmp_path / 'site'
    listed(online, {'index.html': b'<p>viewer</p>', 'assets/main.js': b'let a = 1'})
    server, url = site(online)
    home = tmp_path / 'home'
    (home / 'viewer').mkdir(parents=True)
    (home / 'viewer' / 'stale.js').write_text('old')
    try:
        got = watch.viewer(home, url)
        assert got and sorted(p.relative_to(got).as_posix() for p in got.rglob('*') if p.is_file()) == ['assets/main.js', 'index.html']
        listed(online, {'index.html': b'<p>viewer</p>', 'assets/main.js': b'evil'}, wrong='assets/main.js')
        with pytest.raises(ValueError, match='main.js'):
            watch.viewer(home, url)
        listed(online, {'index.html': b'<p>changed</p>', 'assets/main.js': b'let a = 1'}, bundle_sha='0' * 64)
        with pytest.raises(ValueError, match='bundle'):
            watch.viewer(home, url)
        # pages on the site itself can come back with a script added on the way: only the bundle is fetched
        listed(online, {'index.html': b'<p>changed</p>', 'assets/main.js': b'let a = 1'})
        (online / 'index.html').write_bytes(b'<p>changed</p><script src="beacon.js"></script>')
        assert (watch.viewer(home, url) / 'index.html').read_bytes() == b'<p>changed</p>'
    finally:
        server.shutdown()
    # the site can't be reached: the copy it has still plays
    assert watch.viewer(home, url) == home / 'viewer'
    assert watch.viewer(tmp_path / 'nobody', url) is None


def test_a_listing_cant_reach_outside_the_viewer_folder(tmp_path):
    online = tmp_path / 'site'
    online.mkdir()
    (online / 'files.json').write_text(json.dumps({'files': {'../escape.js': '0' * 64}}))
    server, url = site(online)
    try:
        with pytest.raises(ValueError):
            watch.viewer(tmp_path / 'home', url)
    finally:
        server.shutdown()


def test_the_viewer_pages_are_served_beside_the_api_and_nothing_outside_them(tmp_path):
    pages = tmp_path / 'pages'
    (pages / 'assets').mkdir(parents=True)
    (pages / 'index.html').write_text('<p>viewer</p>')
    (pages / 'assets' / 'main.js').write_text('let a = 1')
    (tmp_path / 'secret.txt').write_text('no')
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(watch.Kept(tmp_path / 'home'), pages))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base + '/?latest&follow') as r:
            assert r.read() == b'<p>viewer</p>' and r.headers['Content-Type'].startswith('text/html')
        with urllib.request.urlopen(base + '/assets/main.js') as r:
            assert r.headers['Content-Type'] == 'text/javascript'
        with urllib.request.urlopen(base + '/api/runs') as r:
            assert json.loads(r.read()) == []
        for path in ('/../secret.txt', '/%2e%2e/secret.txt', '/nothing.js'):
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + path)
            assert e.value.code == 404
    finally:
        server.shutdown()
