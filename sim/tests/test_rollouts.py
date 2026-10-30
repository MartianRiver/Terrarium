from dataclasses import replace

import numpy as np
import torch

from terrarium.brain import SHAPE, Brain, tensors
from terrarium.config import DEFAULT, load, load_train
from terrarium.forage import Observation
from terrarium.ppo import Rollout
from terrarium.rollouts import Collector, OnDevice, seats

# nights, and episodes short enough that arenas run out of time inside a rollout, so the cut-off value is used
NIGHT = load(DEFAULT.parent / 'night.toml')
SHORT = replace(NIGHT, episode=replace(NIGHT.episode, seconds=0.5))
SOLO = load(DEFAULT.parent / 'solo.toml')
TRAIN = load_train()


def play(make, steps=20, rounds=2, memory=0):
    torch.manual_seed(0)
    actor = Brain(**SHAPE)
    if memory:
        actor = actor.with_memory(memory)
        # open the link, so the notes change what it does
        torch.nn.init.normal_(actor.recall.weight, std=0.3)
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


def test_notes_carry_over_rollouts_the_same_both_ways():
    # 15 steps, so a rollout doesn't end where the episodes do (10 ticks) and wipe every note
    old = play(lambda actor: Collector(SHORT, TRAIN, 4, 3, actor), steps=15, memory=8)
    new = play(lambda actor: OnDevice(SHORT, TRAIN, 4, 3, actor), steps=15, memory=8)
    same(old, new)
    # the second rollout starts from the notes the first left
    assert np.abs(old[0][1][0].notes).sum() > 0


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


COLONY = load(DEFAULT.parent / 'colony.toml')


def test_fixed_seats_keep_each_colony_on_its_brain():
    whose = seats([(COLONY, 4), (COLONY, 2)], 3, fixed=True).reshape(6, -1)
    colony = np.repeat(np.arange(COLONY.colonies.count), COLONY.colonies.slots)
    assert (whose == colony % 3).all()


def test_every_brain_takes_every_seat():
    whose = seats([(COLONY, 4), (COLONY, 2)], 3).reshape(6, -1)
    colony = np.repeat(np.arange(COLONY.colonies.count), COLONY.colonies.slots)
    # one brain to a colony in every arena, and over the arenas each brain plays every colony
    for arena in whose:
        assert sorted(set(arena[colony == c][0] for c in range(3))) == [0, 1, 2]
        for c in range(3):
            assert len(set(arena[colony == c])) == 1
    for c in range(3):
        assert set(whose[:, colony == c][:, 0]) == {0, 1, 2}


def sure_of(thrust: float) -> Brain:
    """A brain that always thrusts this hard, near enough."""
    brain = Brain(**SHAPE)
    with torch.no_grad():
        brain.policy.weight.zero_()
        brain.policy.bias[0] = thrust
        brain.log_std[0] = -20
    return brain


def test_each_brain_plays_its_own_colonies():
    rollouts = OnDevice(COLONY, TRAIN, 3, 0, [sure_of(1.0), sure_of(-1.0), sure_of(0.0)])
    try:
        roll, last = rollouts.collect([b.state_dict() for b in rollouts.actors], 2)
    finally:
        rollouts.close()
    thrust = roll.actions[..., 0]
    for k, want in enumerate((1.0, -1.0, 0.0)):
        assert np.allclose(thrust[:, rollouts.whose == k], want, atol=1e-3)
    assert last.shape == (rollouts.samples,)


def test_each_brain_scores_its_own_samples():
    # the log odds and values kept for PPO are the playing brain's own, so its first ratio is exactly 1
    torch.manual_seed(1)
    brains = [Brain(**SHAPE), Brain(**SHAPE), Brain(width=32, layers=2, heads=4)]
    brains[1].to_bernoulli()
    rollouts = OnDevice(COLONY, TRAIN, 3, 0, brains)
    try:
        roll, _ = rollouts.collect([b.state_dict() for b in brains], 3)
    finally:
        rollouts.close()
    flat = lambda x: x.reshape(-1, *x.shape[2:])
    whose = np.tile(rollouts.whose, len(roll.me))
    for k, brain in enumerate(rollouts.actors):
        mine = (whose == k) & flat(roll.active)
        with torch.no_grad():
            obs = Observation(flat(roll.me)[mine], flat(roll.kinds)[mine], flat(roll.rays)[mine])
            mean, value, _ = brain(*tensors(obs, 'cpu'))
            logp = brain.dist(mean).log_prob(torch.from_numpy(flat(roll.actions)[mine])).sum(-1)
        assert np.allclose(logp.numpy(), flat(roll.logprobs)[mine], atol=1e-5)
        assert np.allclose(value.numpy(), flat(roll.values)[mine], atol=1e-5)
