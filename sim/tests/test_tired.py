from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.replay import frame
from terrarium.schema import ACTIONS
from terrarium.world import World

PEEK = load(DEFAULT.parent / 'nursery-peek-again.toml')
TIRED = replace(PEEK, tired=replace(PEEK.tired, drain=0.05, rest=0.1, still=0.2, below=0.3, slowest=0.25))


def go(world, thrust, seconds):
    x = np.zeros((*world.alive.shape, len(ACTIONS)))
    x[..., 2:] = -1
    x[..., 0] = thrust
    for _ in range(round(seconds * world.cfg.tick_hz)):
        world.step(x)


def test_running_flat_out_tires_a_baby_and_resting_brings_it_back():
    world = World(TIRED, 1, seed=0)
    go(world, 1.0, 10)
    assert np.allclose(world.stamina, 0.5, atol=0.01)
    go(world, 1.0, 8)
    tired_speed = np.hypot(*world.vel[0].T).max()
    fresh = World(PEEK, 1, seed=0)
    go(fresh, 1.0, 18)
    assert tired_speed < 0.6 * np.hypot(*fresh.vel[0].T).max()
    go(world, 0.0, 5)
    assert np.all(world.stamina > 0.45)


def test_off_it_changes_nothing():
    a, b = World(PEEK, 2, seed=3), World(replace(PEEK, tired=replace(PEEK.tired, rest=0.5)), 2, seed=3)
    for w in (a, b):
        go(w, 1.0, 5)
    assert np.array_equal(a.pos, b.pos) and np.all(a.stamina == 1)


def test_a_new_episode_starts_rested_and_replays_say_how_tired():
    world = World(TIRED, 1, seed=0)
    go(world, 1.0, 12)
    assert 'stamina' in frame(world, 0)['creatures'][0]
    world.reset(np.array([True]))
    assert np.all(world.stamina == 1)
