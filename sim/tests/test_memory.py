import json
from dataclasses import replace

import numpy as np
import pytest
import torch

from terrarium import load
from terrarium.brain import SHAPE, Brain, save, tensors
from terrarium.brain import load as load_brain
from terrarium.config import DEFAULT, load_train
from terrarium.evals import brain_policy, run
from terrarium.forage import Forage
from terrarium.ppo import Episodes, collect, replay
from terrarium.train import train

from test_ppo import short
from test_widen import outputs


def shaken(brain: Brain, seed: int = 0) -> Brain:
    torch.manual_seed(seed)
    for p in brain.parameters():
        p.data += torch.randn_like(p) * 0.1
    return brain


def moments(n: int = 8, steps: int = 5, seed: int = 1):
    g = torch.Generator().manual_seed(seed)
    s = Brain(**SHAPE).schema
    return [(torch.randn(n, len(s['self']), generator=g), torch.randint(0, 5, (n, 16), generator=g),
             torch.randn(n, 16, len(s['ray']), generator=g)) for _ in range(steps)]


def test_a_brain_given_memory_acts_exactly_as_before():
    old = shaken(Brain(**SHAPE)).eval()
    new = old.with_memory(16).eval()
    assert new.shape == {**SHAPE, 'memory': 16}
    notes = new.blank(8)
    with torch.no_grad():
        for me, kinds, rays in moments():
            mean, value, _ = old(me, kinds, rays)
            mean2, value2, notes = new(me, kinds, rays, notes)
            assert torch.equal(mean, mean2) and torch.equal(value, value2)
    # it writes notes from the start; only reading them back starts at zero
    assert notes.abs().sum() > 0



def test_recall_starts_reading_the_notes_a_little():
    old = shaken(Brain(**SHAPE)).eval()
    new = old.with_memory(16, recall=0.1).eval()
    assert new.recall.weight.abs().sum() > 0 and not new.recall.bias.any()
    notes, gaps = new.blank(8), []
    with torch.no_grad():
        for me, kinds, rays in moments():
            mean, _, _ = old(me, kinds, rays)
            mean2, _, notes = new(me, kinds, rays, notes)
            gaps.append((mean - mean2).abs().max().item())
    # the notes are written before they're read, so they nudge it from the first moment, a little
    assert 0 < min(gaps) and max(gaps) < 0.5

def test_once_the_link_opens_what_it_saw_before_matters_unless_wiped():
    brain = shaken(Brain(**SHAPE).with_memory(16), seed=2).eval()
    a, b = moments(seed=3), moments(seed=4)
    now = moments(steps=1, seed=5)[0]
    with torch.no_grad():
        ends = []
        for past in (a, b):
            notes = brain.blank(8)
            for m in past:
                _, _, notes = brain(*m, notes)
            ends.append(brain(*now, notes)[0])
        assert not torch.allclose(ends[0], ends[1])
        assert torch.equal(brain(*now)[0], brain(*now, brain.blank(8))[0])


def test_memory_saves_and_loads(tmp_path):
    brain = shaken(Brain(**SHAPE).with_memory(8))
    save(brain, tmp_path / 'b.pt')
    again, _ = load_brain(tmp_path / 'b.pt')
    assert again.memory == 8 and again.shape['memory'] == 8
    for x, y in zip(outputs(brain), outputs(again)):
        assert torch.equal(x, y)


def test_a_brain_from_before_memory_loads_without_it(tmp_path):
    brain = Brain(**SHAPE)
    save(brain, tmp_path / 'b.pt')
    data = torch.load(tmp_path / 'b.pt', weights_only=True)
    data['shape'].pop('memory')
    torch.save(data, tmp_path / 'old.pt')
    old, _ = load_brain(tmp_path / 'old.pt')
    assert old.memory == 0 and old.shape == SHAPE


def test_memory_is_added_once():
    with pytest.raises(ValueError, match='already has memory'):
        Brain(**SHAPE).with_memory(8).with_memory(8)


def test_the_update_replays_each_stream_as_it_was_played():
    """Played again from the rollout's starting notes, wiped where they were wiped, every living choice gets the value
    it had while collecting, through deaths and fresh episodes inside the rollout."""
    cfg = load(DEFAULT.parent / 'colony.toml')
    # episodes of 1.5 s, so arenas start over in the middle of a 40-step rollout
    cfg = replace(cfg, episode=replace(cfg.episode, seconds=1.5))
    env = Forage(cfg, load_train(), 2, seed=0)
    actor = shaken(Brain(**SHAPE).with_memory(16), seed=6)
    notes = actor.blank(env.samples)
    obs, episodes = env.observe(), Episodes(env.samples, cfg.dt)
    # a first rollout, so the second starts from notes that aren't blank
    _, obs, notes = collect(env, actor, 7, obs, episodes, notes)
    roll, _, _ = collect(env, actor, 40, obs, episodes, notes)
    assert roll.dones.any() and np.abs(roll.notes).sum() > 0
    t = lambda x: torch.from_numpy(np.ascontiguousarray(x))
    with torch.no_grad():
        mean, value = replay(actor, t(roll.me), t(roll.kinds), t(roll.rays), t(roll.notes[0]),
                             t(roll.active & ~roll.dones).float())
        logp = actor.dist(mean).log_prob(t(roll.actions).flatten(0, 1)).sum(-1).numpy()
    live = roll.active.reshape(-1)
    assert np.allclose(value.numpy()[live], roll.values.reshape(-1)[live], atol=1e-5)
    assert np.allclose(logp[live], roll.logprobs.reshape(-1)[live], atol=1e-4)


def test_evals_carry_notes_and_can_wipe_them(tmp_path):
    cfg = load(DEFAULT.parent / 'solo.toml')
    cfg = replace(cfg, episode=replace(cfg.episode, seconds=3.0))
    save(shaken(Brain(**SHAPE).with_memory(8), seed=7), tmp_path / 'b.pt')
    kept = run(cfg, brain_policy(tmp_path / 'b.pt'), episodes=2)
    wiped = run(cfg, brain_policy(tmp_path / 'b.pt', wiped=True), episodes=2)
    again = run(cfg, brain_policy(tmp_path / 'b.pt'), episodes=2)
    assert kept['seconds_alive'] == again['seconds_alive'] and kept['food_per_minute'] == again['food_per_minute']
    assert json.dumps(kept, sort_keys=True) != json.dumps(wiped, sort_keys=True)


def test_training_with_memory(tmp_path):
    world, trainer = short(tmp_path)
    run_ = train('mem', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu', memory=8, score=False)
    record = json.loads((run_.dir / 'run.json').read_text())
    assert record['shape']['memory'] == 8
    trained, _ = load_brain(run_.dir / 'checkpoints' / '00000000256.pt')
    assert trained.memory == 8 and trained.recall.weight.abs().sum() > 0
