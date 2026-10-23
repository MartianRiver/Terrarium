from dataclasses import replace

import numpy as np
import pytest
import torch

from terrarium import load, schema, vision
from terrarium.brain import SHAPE, Brain, brain_id, save, tensors
from terrarium.brain import load as load_brain
from terrarium.config import DEFAULT, load_train
from terrarium.evals import brain_policy, run
from terrarium.forage import Forage
from terrarium.schema import SchemaError

SOLO = load(DEFAULT.parent / 'solo.toml')
REWARD = load_train().reward


def observation(seed=0, kinds=len(schema.KINDS), batch=32, rays=16):
    g = torch.Generator().manual_seed(seed)
    return (torch.randn(batch, len(schema.SELF), generator=g), torch.randint(0, kinds, (batch, rays), generator=g),
            torch.randn(batch, rays, len(schema.RAY), generator=g))


def test_kinds_are_in_visions_order():
    assert [getattr(vision, k.upper()) for k in schema.KINDS] == list(range(len(schema.KINDS)))


def test_schema_takes_its_own_and_older():
    schema.check(schema.current())
    old = schema.current() | {'self': schema.current()['self'][:2], 'kinds': ['nothing', 'wall']}
    schema.check(old)


def test_schema_refuses_a_renamed_input():
    renamed = schema.current()
    renamed['ray'] = ['distance', 'angle', 'cos']
    with pytest.raises(SchemaError, match=r"ray\[1\] is 'angle' in the brain .* but 'sin' here"):
        schema.check(renamed)


def test_schema_refuses_a_newer_brain():
    newer = schema.current()
    newer['actions'] = newer['actions'] + ['signal']
    with pytest.raises(SchemaError, match="has actions this code doesn't .*: signal"):
        schema.check(newer)


def test_checkpoint_round_trip(tmp_path):
    torch.manual_seed(0)
    brain = Brain(**SHAPE)
    path = tmp_path / 'b.pt'
    first = save(brain, path, run='test', step=3)
    again, meta = load_brain(path)
    assert meta == {'run': 'test', 'step': 3} and first == brain_id(path)
    obs = observation()
    for a, b in zip(brain(*obs), again(*obs)):
        assert torch.equal(a, b)


def test_a_brain_from_shorter_lists_acts_the_same(tmp_path):
    """Grown lists load as zero weights: the old brain's actions and values come out unchanged."""
    torch.manual_seed(1)
    now = schema.current()
    old = now | {'self': now['self'][:3], 'ray': now['ray'][:2], 'kinds': now['kinds'][:3], 'actions': now['actions'][:1]}
    brain = Brain(**SHAPE, lists=old)
    save(brain, tmp_path / 'old.pt')
    grown, _ = load_brain(tmp_path / 'old.pt')

    me, kinds, rays = observation(kinds=3)
    mean, value = brain(me[:, :3], kinds, rays[..., :2])
    mean2, value2 = grown(me, kinds, rays)
    assert torch.allclose(value, value2, atol=1e-6)
    assert torch.allclose(mean, mean2[:, :1], atol=1e-6)
    assert (mean2[:, 1] == 0).all()


def test_not_a_brain_is_refused(tmp_path):
    torch.save({'weights': {}}, tmp_path / 'x.pt')
    with pytest.raises(SchemaError, match="isn't a Terrarium brain"):
        load_brain(tmp_path / 'x.pt')


def test_forage_observes_every_creature():
    env = Forage(SOLO, REWARD, 3, seed=0)
    obs = env.observe()
    rays = SOLO.vision.rays
    assert obs.me.shape == (3, len(schema.SELF)) and obs.kinds.shape == (3, rays)
    assert obs.rays.shape == (3, rays, len(schema.RAY)) and obs.me.dtype == obs.rays.dtype == np.float32
    assert (obs.rays[..., 0] <= 1).all() and (obs.me[:, 0] == SOLO.energy.start).all()
    mean, value = Brain(**SHAPE)(*tensors(obs, 'cpu'))
    assert mean.shape == (3, len(schema.ACTIONS)) and value.shape == (3,)


def test_forage_rewards_eating_and_dying_and_starts_over():
    env = Forage(SOLO, REWARD, 2, seed=0)
    w = env.world
    w.food_pos[0, 0] = w.pos[0, 0]
    w.energy[1, 0] = 0.0001
    w.food_regrow[1] = 1
    _, reward, done, ended = env.step(np.zeros((2, 2)))
    assert reward[0] == pytest.approx(REWARD.food) and reward[1] == pytest.approx(REWARD.death)
    assert list(done) == [False, True] and list(ended) == [False, True]
    # arena 1 has already started over
    assert w.alive[1, 0] and w.age[1] == 0 and w.energy[1, 0] == SOLO.energy.start


def test_forward_and_side_speed():
    env = Forage(replace(SOLO, block=()), REWARD, 1, seed=0)
    env.world.heading[:] = np.pi / 2
    obs = env.observe()
    for _ in range(20):
        obs, *_ = env.step(np.array([[1.0, 0.0]]))
    assert obs.me[0, 1] == pytest.approx(1.0, abs=0.02) and abs(obs.me[0, 2]) < 0.02
    assert list(obs.me[0, 3:5]) == [1.0, 0.0]


def test_home_sense():
    env = Forage(replace(SOLO, block=()), REWARD, 1, seed=0)
    w = env.world
    w.physics.bodies[0][0].position = tuple(w.nests[0] + (3.0, 0))
    w.physics.read()
    home = slice(len(schema.SELF) - 3, None)
    w.heading[:] = np.pi
    assert list(env.observe().me[0, home]) == pytest.approx([3.0 / SOLO.vision.range, 0, 1], abs=1e-6)
    # facing up, home is a quarter turn to its left
    w.heading[:] = np.pi / 2
    assert list(env.observe().me[0, home]) == pytest.approx([3.0 / SOLO.vision.range, 1, 0], abs=1e-6)


def test_evals_take_a_brain(tmp_path):
    torch.manual_seed(2)
    save(Brain(**SHAPE), tmp_path / 'b.pt')
    short = replace(SOLO, episode=replace(SOLO.episode, seconds=5.0))
    r = run(short, brain_policy(tmp_path / 'b.pt'), 2)
    assert 0 < r['seconds_alive']['mean'] <= 5.0
