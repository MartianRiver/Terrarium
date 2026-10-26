from dataclasses import replace

import numpy as np
import torch

from terrarium.brain import SHAPE, Brain
from terrarium.config import DEFAULT, load, load_train
from terrarium.ppo import Rollout
from terrarium.rollouts import Collector, OnDevice

# nights, and episodes short enough that arenas run out of time inside a rollout, so the cut-off value is used
NIGHT = load(DEFAULT.parent / 'night.toml')
SHORT = replace(NIGHT, episode=replace(NIGHT.episode, seconds=0.5))
SOLO = load(DEFAULT.parent / 'solo.toml')
TRAIN = load_train()


def play(make, steps=20, rounds=2):
    torch.manual_seed(0)
    actor = Brain(**SHAPE)
    state = {k: v.clone() for k, v in actor.state_dict().items()}
    torch.manual_seed(7)
    rollouts = make(actor)
    try:
        out = [rollouts.collect(state, steps) for _ in range(rounds)]
        return out, rollouts.episodes.take()
    finally:
        rollouts.close()


def same(a, b):
    for (ra, va), (rb, vb) in zip(a[0], b[0]):
        for k in Rollout.__dataclass_fields__:
            assert np.array_equal(getattr(ra, k), getattr(rb, k)), k
        assert np.array_equal(va, vb)
    assert a[1] == b[1]


def test_one_worker_on_the_cpu_plays_exactly_what_collector_does():
    old = play(lambda actor: Collector(SHORT, TRAIN, 4, 3, actor))
    new = play(lambda actor: OnDevice(SHORT, TRAIN, 4, 3, actor))
    same(old, new)
    assert old[0][0][0].dones.any()


def test_mixed_worlds_get_the_seeds_collector_gives_them():
    # each share samples from the same generator in turn here, so only the worlds can be compared: their first
    # observations, before anything is sampled
    mix = [(SOLO, 2)]
    old = Collector(SHORT, TRAIN, 4, 3, Brain(**SHAPE), mix=mix)
    new = OnDevice(SHORT, TRAIN, 4, 3, Brain(**SHAPE), mix=mix)
    firsts = np.concatenate([s.obs.me for s in old.local])
    assert np.array_equal(firsts, new.obs.me)
    assert new.samples == old.samples


def test_worlds_in_workers_join_up_in_order():
    rolls, episodes = play(lambda actor: OnDevice(SHORT, TRAIN, 4, 3, actor, workers=2), steps=40, rounds=1)
    roll, last = rolls[0]
    samples = 4 * SHORT.colonies.count * SHORT.colonies.size
    assert roll.me.shape[:2] == (40, samples) and last.shape == (samples,)
    assert roll.dones.any() and episodes['episodes'] > 0
    # the workers' worlds are seeded as Collector's are, so their first steps see the same
    old = Collector(SHORT, TRAIN, 4, 3, Brain(**SHAPE), workers=2)
    try:
        first, _ = old.collect(Brain(**SHAPE).state_dict(), 1)
    finally:
        old.close()
    assert np.array_equal(first.me[0], roll.me[0])
