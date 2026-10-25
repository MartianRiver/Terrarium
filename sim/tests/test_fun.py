from dataclasses import replace

import numpy as np

from terrarium.config import DEFAULT, load, load_train
from terrarium.forage import Forage
from terrarium.fun import BORED_TICKS, Fun
from terrarium.world import World

VAULT = load(DEFAULT.parent / 'vault.toml')
# just outside the east door, touching its outer face
OUTSIDE = (3.1 + VAULT.creature.radius + 0.05, 0.0)


def at_door():
    cfg = replace(VAULT, colonies=replace(VAULT.colonies, count=1, size=1))
    world = World(cfg)
    world.physics.place([0], np.array([[OUTSIDE]]))
    world.heading[:] = 0.0
    world.clock[:] = 30.0
    return world


def pull(world, fun, seconds, grab=1):
    got = 0.0
    for _ in range(round(seconds * world.cfg.tick_hz)):
        actions = np.array([[[1.0, 0.0, -1, -1, -1, grab]]])
        world.step(actions)
        got += fun.step(actions)[0, 0]
    return got


def test_moving_a_block_is_fun_and_wears_off():
    world = at_door()
    fun = Fun(world, novelty=1.0, variety=0.0)
    first = pull(world, fun, 1.5)
    assert world.block_pos[0, 6, 0] > 3.5
    assert first > 0
    world.physics.shift([0], [6], np.array([[2.85, 0.0]]), np.array([0.0]))
    world.physics.place([0], np.array([[OUTSIDE]]))
    fun.blocks = world.block_pos.copy()
    again = pull(world, fun, 1.5)
    assert 0 < again < first


def test_walking_about_without_moving_anything_is_no_fun():
    world = World(replace(VAULT, colonies=replace(VAULT.colonies, count=1, size=1)))
    fun = Fun(world, novelty=1.0, variety=0.0)
    assert pull(world, fun, 1.0, grab=-1) == 0


def test_a_new_action_is_fun_until_it_isnt():
    world = World(replace(VAULT, colonies=replace(VAULT.colonies, count=1, size=1)))
    fun = Fun(world, novelty=0.0, variety=1.0)
    yes = np.array([[[0.0, 0.0, -1, -1, -1, 1]]])
    first = fun.step(yes)[0, 0]
    later = [fun.step(yes)[0, 0] for _ in range(BORED_TICKS * 2)][-1]
    assert first == 1.0 and later < 0.3
    assert fun.step(np.array([[[0.0, 0.0, -1, -1, 1, -1]]]))[0, 0] == 1.0


def test_off_unless_asked_for():
    assert Forage(VAULT, load_train(), 1, 0).fun is None
