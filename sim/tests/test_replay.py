import json

import numpy as np

from terrarium import load, replay
from terrarium.record import record

TICKS = 400


def test_round_trip(tmp_path):
    cfg = load()
    path = tmp_path / 'r.jsonl.gz'
    world = record(cfg, path, TICKS, seed=3)
    head, frames = replay.read(path)

    assert head['version'] == replay.VERSION
    assert head['info']['width'] == cfg.arena.size and head['info']['tickHz'] == cfg.tick_hz
    assert len(head['info']['nests']) == cfg.colonies.count
    assert head['source']['seed'] == 3 and head['source']['config'] == json.loads(json.dumps(cfg.to_dict()))
    assert [f['tick'] for f in frames] == list(range(TICKS + 1))

    last = frames[-1]
    assert [c['id'] for c in last['creatures']] == list(world.creature_id)
    pos = np.array([[c['x'], c['y']] for c in last['creatures']])
    assert np.abs(pos - world.pos[0]).max() <= 0.0005
    assert len(last['food']) == world.food_present[0].sum()
    assert [b['id'] for b in last['blocks']] == list(world.block_id)


def test_food_ids_never_come_back(tmp_path):
    # the viewer pops food in and out by id, so a regrown food needs a new one
    path = tmp_path / 'r.jsonl.gz'
    world = record(load(), path, TICKS, seed=1)
    assert world.eaten > 0
    _, frames = replay.read(path)
    gone, before = set(), set()
    for f in frames:
        now = {food['id'] for food in f['food']}
        assert len(now) == len(f['food'])
        assert not now & gone
        gone |= before - now
        before = now


def test_same_run_same_bytes(tmp_path):
    a, b = tmp_path / 'a.jsonl.gz', tmp_path / 'b.jsonl.gz'
    record(load(), a, 50, seed=2)
    record(load(), b, 50, seed=2)
    assert a.read_bytes() == b.read_bytes()
