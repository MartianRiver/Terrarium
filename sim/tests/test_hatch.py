from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, Config, build, load_train, upgrade
from terrarium.forage import Forage
from terrarium.world import World

NIGHT = load(DEFAULT.parent / 'night.toml')
HATCH = replace(NIGHT, hatch=replace(NIGHT.hatch, cost=3, threshold=5, seconds=1.0))
STILL = np.zeros((1, 18, 6))


def lose_one(cfg=HATCH, store=6):
    world = World(cfg)
    world.store[0, 0] = store
    world.energy[0, 1] = 1e-6
    world.step(STILL)
    assert not world.alive[0, 1]
    return world


def ticks(world, seconds):
    for _ in range(round(seconds * world.cfg.tick_hz)):
        world.step(STILL)


def test_a_colony_pays_for_an_egg_that_hatches_in_the_lost_ones_place():
    world = lose_one()
    old = world.creature_id[0, 1]
    assert world.store[0, 0] == 3 and world.egg[0, 1] > 0
    ticks(world, 0.95)
    assert not world.alive[0, 1]
    ticks(world, 0.1)
    assert world.alive[0, 1] and world.hatched[0, 0] == 1
    assert world.energy[0, 1] == pytest.approx(NIGHT.energy.start, abs=0.01)
    assert world.nest_at()[0, 1] == 0
    # a new creature, as the viewer sees it
    assert world.creature_id[0, 1] != old and world.creature_id[0, 1] not in world.food_id[0]
    # one egg only: the store is under the threshold now
    world.energy[0, 2] = 1e-6
    ticks(world, 2)
    assert not world.alive[0, 2] and world.store[0, 0] == 3


def test_no_egg_below_the_threshold_or_with_hatching_off():
    assert lose_one(store=4).egg.sum() == 0
    off = lose_one(NIGHT)
    ticks(off, 2)
    assert not off.alive[0, 1] and off.store[0, 0] == 6


def test_a_colony_with_nobody_left_loses_its_eggs():
    world = lose_one()
    world.energy[0, :6] = 1e-6
    ticks(world, 2)
    assert not world.alive[0, :6].any() and world.hatched[0, 0] == 0


def test_starting_over_forgets_eggs_and_hatchlings():
    world = lose_one()
    ticks(world, 1.1)
    world.reset(np.ones(1, bool))
    assert world.hatched.sum() == 0 and world.egg.sum() == 0
    assert list(world.creature_id[0]) == list(range(1, 19))


def test_training_pays_the_colony_and_the_hatchling_acts_again():
    train = load_train()
    env = Forage(HATCH, replace(train, reward=replace(train.reward, hatch=1.0, colony=0.0)), 1, 0)
    env.world.store[0, 0] = 6
    env.world.energy[0, 1] = 1e-6
    env.step(np.zeros((18, 6)))
    assert not env.active[1]
    paid = 0.0
    # a second of egg, a choice at a time
    for _ in range(round(1.1 * HATCH.tick_hz / train.ppo.repeat)):
        _, reward, _, _ = env.step(np.zeros((18, 6)))
        paid = max(paid, reward[0])
    assert env.active[1] and paid > 0.9
    # nothing for another colony
    assert env.world.hatched[0, 1:].sum() == 0


def test_old_run_records_load_with_hatching_off():
    recorded = load(DEFAULT).to_dict()
    del recorded['hatch']
    assert not build(Config, upgrade(recorded)).hatch.on
