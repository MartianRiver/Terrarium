import gzip
import json
from dataclasses import replace

import torch

from terrarium import load
from terrarium.brain import Brain, save
from terrarium.config import DEFAULT
from terrarium.mind import think, track, wiring
from terrarium.record import record

COLONY = load(DEFAULT.parent / 'colony.toml')


def lines(path):
    with gzip.open(path, 'rt') as f:
        return [json.loads(line) for line in f]


def test_thinking_step_by_step_is_the_brain_s_own_forward_pass():
    brain = Brain(32, 2, 4).eval()
    me, kinds, rays = torch.randn(5, 19), torch.randint(0, 6, (5, 16)), torch.randn(5, 16, 6)
    attention, units, _, mean, value = think(brain, me, kinds, rays)
    want_mean, want_value, _ = brain(me, kinds, rays)
    assert torch.allclose(mean, want_mean, atol=1e-5) and torch.allclose(value, want_value, atol=1e-5)
    # each head's weights from the self token over itself and the 16 rays add up to 1
    assert attention.shape == (2, 5, 4, 17) and torch.allclose(attention.sum(-1), torch.ones(2, 5, 4))
    assert units.shape == (3, 5, 32) and torch.allclose(units[0], brain.me(me))


def test_wiring_keeps_the_strongest_connections_into_each_unit():
    brain = Brain(32, 2, 4)
    w, me = wiring(brain, 3), brain.me.weight.detach()
    assert len(w['senses']) == 32 * 3 and len(w['layers']) == 2 and len(w['layers'][0]) == 32 * 3
    to, frm, weight = w['senses'][0]
    assert weight == round(float(me[to, frm]), 4)
    assert abs(weight) == round(float(me[to].abs().max()), 4)
    assert {t for t, _, _ in w['actions']} == set(range(6)) and len(w['value']) == 9


def test_a_mind_follows_its_terrikin_through_the_replay(tmp_path):
    cfg = replace(COLONY, episode=replace(COLONY.episode, seconds=6.0))
    torch.manual_seed(0)
    save(Brain(32, 2, 4), tmp_path / 'b.pt', repeat=2)
    record(cfg, tmp_path / 'r.jsonl.gz', 60, seed=3, brain=tmp_path / 'b.pt')
    frames = {f['tick']: f for f in lines(tmp_path / 'r.jsonl.gz')[1:]}
    who = frames[0]['creatures'][4]['id']
    track(cfg, tmp_path / 'b.pt', tmp_path / 'm.jsonl.gz', 3, who, 60)
    head, *minds = lines(tmp_path / 'm.jsonl.gz')
    assert head['creature'] == who and head['brain']['repeat'] == 2 and head['rays']['count'] == 16
    # it chooses every other tick, and is where the replay has it each time
    assert [m['tick'] for m in minds] == list(range(0, 60, 2))
    for m in minds:
        c = next(c for c in frames[m['tick']]['creatures'] if c['id'] == who)
        assert (m['x'], m['y']) == (c['x'], c['y'])
    m = minds[0]
    assert len(m['self']) == len(head['brain']['schema']['self']) and len(m['kinds']) == 16
    assert len(m['attention']) == 2 and len(m['attention'][0]) == 4 and len(m['summary']) == 32
    assert len(m['units']) == 3 and len(m['units'][0]) == 32
    odds = dict(zip(head['brain']['schema']['actions'], m['odds']))
    assert odds['thrust'] is None and 0 < odds['sprint'] < 1
