from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, ConfigError
from terrarium.forage import observe
from terrarium.schema import ACTIONS, SELF
from terrarium.world import World

TREE = load(DEFAULT.parent / 'nursery-tree.toml')
JUMP = ACTIONS.index('jump')


def act(jump=False):
    out = np.full((1, 1, len(ACTIONS)), -1.0)
    out[..., :2] = 0
    out[..., JUMP] = 1.0 if jump else -1.0
    return out


def under_an_apple(world):
    """Stand the baby right under the first apple."""
    world.physics.place(np.array([0]), world.food_pos[:1, :1].copy())


def test_a_jump_rises_its_height_and_comes_back_down():
    world = World(TREE)
    world.step(act(True))
    top = 0.0
    for _ in range(40):
        world.step(act())
        top = max(top, world.z[0, 0])
    assert TREE.jump.height * 0.85 < top <= TREE.jump.height
    assert world.z[0, 0] == 0 and world.jumps[0, 0] == 1


def test_no_jump_from_the_air():
    world = World(TREE)
    world.step(act(True))
    world.step(act(True))
    assert world.jumps[0, 0] == 1


def test_apples_hang_round_the_trunk():
    world = World(TREE, 8, seed=3)
    gap = np.hypot(*world.food_pos[:, :TREE.food.count].transpose(2, 0, 1))
    assert (gap >= TREE.tree.near - 1e-9).all() and (gap <= TREE.tree.far + 1e-9).all()


def test_standing_under_one_isnt_enough():
    world = World(TREE)
    under_an_apple(world)
    for _ in range(20):
        world.step(act())
    assert world.meals[0, 0] == 0


def test_jumping_under_one_takes_it_and_pays_even_when_full():
    world = World(TREE)
    world.energy[:] = 1.0
    under_an_apple(world)
    world.step(act(True))
    for _ in range(20):
        world.step(act())
    assert world.meals[0, 0] >= 1
    assert world.tree.points(world.alive)[0, 0] == world.meals[0, 0] * TREE.tree.points
    assert world.tree.points(world.alive)[0, 0] == 0


def test_the_brain_feels_how_high_it_is():
    world = World(TREE)
    world.step(act(True))
    world.step(act())
    obs = observe(world, np.zeros((1, 1, 2)))
    assert 0 < obs.me[0, SELF.index('height')] <= 1


def test_a_branch_out_of_reach_is_refused():
    with pytest.raises(ConfigError):
        World(replace(TREE, tree=replace(TREE.tree, reach=TREE.jump.height)))
