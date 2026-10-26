import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from terrarium import replay, serve
from terrarium.brain import SHAPE, Brain, save
from terrarium.config import DEFAULT, load

SOLO = DEFAULT.parent / 'solo.toml'


def make_run(root, name, started, finished=None, rows=(), checkpoints=()):
    run = root / name
    (run / 'checkpoints').mkdir(parents=True)
    rec = {'id': name, 'started': started, 'scratch': False, 'world': {'file': 'solo.toml', 'config': load(SOLO).to_dict()},
           'train': {'config': {'ppo': {'samples': 1000}}}}
    if finished:
        rec['finished'] = finished
    (run / 'run.json').write_text(json.dumps(rec))
    (run / 'metrics.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    for samples in checkpoints:
        save(Brain(**SHAPE), run / 'checkpoints' / f'{samples:011d}.pt')
    return run


def test_runs_are_live_finished_or_stopped_newest_first(tmp_path):
    make_run(tmp_path, 'done', '2026-10-23T10:00:00+1100', '2026-10-23T10:30:00+1100', [{'samples': 1000, 'seconds': 1}])
    stopped = make_run(tmp_path, 'stopped', '2026-10-23T11:00:00+1100', rows=[{'samples': 500, 'seconds': 1}])
    old = time.time() - 600
    os.utime(stopped / 'run.json', (old, old))
    os.utime(stopped / 'metrics.jsonl', (old, old))
    live = make_run(tmp_path, 'live', '2026-10-23T12:00:00+1100', rows=[{'samples': 200, 'seconds': 1}])
    # halfway through writing the next row
    with open(live / 'metrics.jsonl', 'a') as f:
        f.write('{"samples": 3')
    # a pod's run: named in UTC, started after the others
    make_run(tmp_path, '20261023-020000-pod', '2026-10-23T02:00:00+0000')
    runs = serve.Runs(tmp_path).list()
    assert [(r['id'], r['state'], r['samples']) for r in runs] == [
        ('20261023-020000-pod', 'live', 0), ('live', 'live', 200), ('stopped', 'stopped', 500), ('done', 'finished', 1000)]


def test_a_replay_is_recorded_once_in_the_runs_world(tmp_path):
    run = make_run(tmp_path, 'done', '2026-10-23T10:00:00+1100', '2026-10-23T10:30:00+1100', checkpoints=[32768])
    runs = serve.Runs(tmp_path)
    assert [c['samples'] for c in runs.detail('done')['checkpoints']] == [32768]
    path = runs.replay('done', '00000032768.pt', 3)
    head, frames = replay.read(path)
    assert head['source']['seed'] == 3 and head['source']['brain']['file'] == '00000032768.pt'
    assert len(frames) > 1 and len(head['info']['nests']) == 1
    made = path.stat().st_mtime_ns
    assert runs.replay('done', '00000032768.pt', 3).stat().st_mtime_ns == made
    assert runs.replay('done', 'random', 3).name == 'random-3.jsonl.gz'
    assert sorted(p.name for p in (run / 'replays').iterdir()) == ['00000032768-3.jsonl.gz', 'random-3.jsonl.gz']
    with pytest.raises(serve.NotFound):
        runs.replay('done', '../run.json', 0)
    with pytest.raises(serve.NotFound):
        runs.detail('..')


def test_a_mind_is_recorded_once_beside_its_replay(tmp_path):
    run = make_run(tmp_path, 'done', '2026-10-23T10:00:00+1100', '2026-10-23T10:30:00+1100', checkpoints=[32768])
    runs = serve.Runs(tmp_path)
    _, frames = replay.read(runs.replay('done', '00000032768.pt', 3))
    who = frames[0]['creatures'][0]['id']
    path = runs.mind('done', '00000032768.pt', 3, who)
    assert path.name == f'00000032768-3.mind-{who}.jsonl.gz'
    made = path.stat().st_mtime_ns
    assert runs.mind('done', '00000032768.pt', 3, who).stat().st_mtime_ns == made
    assert runs.replay('done', '00000032768.pt', 3, here=True).name == '00000032768-3-here.jsonl.gz'
    with pytest.raises(serve.NotFound):
        runs.mind('done', 'random', 3, who)


def test_the_api_answers_and_refuses(tmp_path):
    make_run(tmp_path, 'done', '2026-10-23T10:00:00+1100', '2026-10-23T10:30:00+1100')
    server = serve.serve(tmp_path, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}/api'
    try:
        with urllib.request.urlopen(base + '/runs') as r:
            assert [run['id'] for run in json.load(r)] == ['done']
        for path, status in [('/runs/nope', 404), ('/elsewhere', 404), ('/runs/done/replay/random?seed=x', 400)]:
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + path)
            assert e.value.code == status and 'error' in json.load(e.value)
    finally:
        server.shutdown()
