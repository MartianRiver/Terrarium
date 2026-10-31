import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.forage import observe
from terrarium.hearing import heard
from terrarium.schema import SELF
from terrarium.world import World

TAG = load(DEFAULT.parent / 'nursery-tag-hide.toml')


def two_apart(gap, behind=True):
    world = World(TAG, 1, seed=0)
    world.alive[0, 2:] = False
    world.pos[0, 0] = (0.0, 0.0)
    world.heading[0, 0] = 0.0
    centres = gap + 2 * TAG.creature.radius
    world.pos[0, 1] = (-centres, 0.0) if behind else (0.0, centres)
    return world


def test_one_close_behind_is_heard_from_behind():
    loud, sin, cos = heard(two_apart(0.6))
    assert np.isclose(loud[0, 0], 1 - 0.6 / TAG.hearing.range)
    assert np.isclose(cos[0, 0], -1) and np.isclose(sin[0, 0], 0, atol=1e-9)


def test_which_side_it_is_on():
    loud, sin, cos = heard(two_apart(1.0, behind=False))
    assert np.isclose(sin[0, 0], 1) and np.isclose(cos[0, 0], 0, atol=1e-9)


def test_nobody_in_range_or_alive_is_silent():
    far = heard(two_apart(TAG.hearing.range + 0.5))
    assert all(np.all(x[0, 0] == 0) for x in far)
    gone = two_apart(0.5)
    gone.alive[0, 1] = False
    assert all(x[0, 0] == 0 for x in heard(gone))
    assert all(x[0, 1] == 0 for x in heard(gone))


def test_off_hears_nothing_and_the_brain_sees_it_last():
    world = World(load(DEFAULT.parent / 'nursery-peek-again.toml'), 2, seed=0)
    assert all(np.all(x == 0) for x in heard(world))
    obs = observe(World(TAG, 2, seed=0), np.zeros((2, TAG.colonies.size, 2)))
    assert obs.me.shape[-1] == len(SELF) and SELF[-3:] == ('heard', 'heard_sin', 'heard_cos')
