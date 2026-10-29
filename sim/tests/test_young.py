from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.forage import observe
from terrarium.schema import SELF
from terrarium.world import World

YOUNG = load(DEFAULT.parent / 'colony-young.toml')
# the night world's hatching, quick, with young hatchlings and no cold (the dawn's would land on the grown one only,
# away from the nest)
NIGHT = load(DEFAULT.parent / 'night.toml')
HATCH = replace(NIGHT, hatch=replace(NIGHT.hatch, cost=3, threshold=5, seconds=1.0), young=YOUNG.young,
                night=replace(NIGHT.night, cold=0.0))


def ticks(world, seconds, actions=None):
    for _ in range(round(seconds * world.cfg.tick_hz)):
        world.step(np.zeros((1, len(world.colony), 6)) if actions is None else actions)


def hatchling(cfg=HATCH):
    """A world where slot 1 died and hatched again, young, with slot 0 a grown one beside it."""
    world = World(cfg)
    world.store[0, 0] = 6
    world.energy[0, 1] = 1e-6
    ticks(world, 1.1)
    assert world.alive[0, 1] and world.young[0, 1] > 0 and world.young[0, 0] == 0
    return world


def test_a_hatchling_is_young_for_a_while_then_grown():
    world = hatchling()
    assert world.young[0, 1] == pytest.approx(YOUNG.young.seconds * YOUNG.tick_hz, abs=1)
    world.young[0, 1] = 3
    ticks(world, 0.2)
    assert world.young[0, 1] == 0


def test_being_young_is_cheaper_and_slower():
    world = hatchling()
    world.energy[0, :2] = 1.0
    go = np.zeros((1, len(world.colony), 6))
    go[0, :2, 0] = 1.0
    ticks(world, 1.0, go)
    spent = 1.0 - world.energy[0, :2]
    assert spent[1] == pytest.approx(spent[0] * YOUNG.young.energy, rel=1e-6)
    speed = np.hypot(*world.vel[0, :2].T)
    assert speed[1] == pytest.approx(speed[0] * YOUNG.young.speed, rel=0.05)


def test_the_young_eat_from_the_store_without_being_hungry_a_bite_their_size():
    world = hatchling()
    assert world.nest_at()[0, 1] == world.colony[1]
    eat = np.zeros((1, len(world.colony), 6))
    eat[0, 1, 3] = 1.0
    jelly = YOUNG.jelly.energy
    # room for 0.3 of the 0.4 a jelly gives: it fills up, for 0.75 of a jelly at half the cost, 0.375
    world.energy[0, 1] = 0.7
    store = world.store[0, 0]
    world.step(eat)
    bite = 0.3 / jelly * YOUNG.young.energy
    # (a tick's drain comes first)
    assert world.jelly[0, 1] == pytest.approx(bite, abs=1e-3) and world.store[0, 0] == pytest.approx(store - bite, abs=1e-3)
    assert world.energy[0, 1] == pytest.approx(1.0, abs=1e-3)
    # emptier, a whole jelly's worth, for half a jelly
    world.energy[0, 1] = 0.2
    world.step(eat)
    assert world.jelly[0, 1] == pytest.approx(bite + YOUNG.young.energy, abs=1e-3)
    assert world.energy[0, 1] == pytest.approx(0.2 + jelly, abs=1e-3)
    # a grown one that full is refused
    world.young[0, 1] = 0
    world.energy[0, 1] = 0.7
    world.step(eat)
    assert world.jelly[0, 1] == pytest.approx(bite + YOUNG.young.energy, abs=1e-3)


def test_the_young_sense_how_young_they_are():
    world = hatchling()
    me = observe(world, np.zeros((1, len(world.colony), 2))).me.reshape(len(world.colony), -1)
    i = SELF.index('young')
    assert me[1, i] == pytest.approx(1.0, abs=0.01) and me[0, i] == 0


def test_young_is_off_everywhere_but_its_own_world():
    for name in ('world', 'solo', 'night', 'colony', 'spots', 'blocks', 'vault'):
        assert not load(DEFAULT.parent / f'{name}.toml').young.on
    assert YOUNG.young.on
    world = World(replace(HATCH, young=NIGHT.young))
    world.store[0, 0] = 6
    world.energy[0, 1] = 1e-6
    ticks(world, 1.1)
    assert world.alive[0, 1] and world.young[0, 1] == 0


def test_the_last_bite_takes_what_the_young_left():
    world = hatchling()
    assert world.nest_at()[0, 1] == world.colony[1]
    eat = np.zeros((1, len(world.colony), 6))
    eat[0, 1, 3] = 1.0
    # grown now, hungry, with a quarter of a jelly left
    world.young[0, 1] = 0
    world.store[0, 0] = 0.25
    world.energy[0, 1] = 0.3
    world.step(eat)
    assert world.store[0, 0] == pytest.approx(0) and world.jelly[0, 1] == pytest.approx(0.25)
    assert world.energy[0, 1] == pytest.approx(0.3 + 0.25 * YOUNG.jelly.energy, abs=1e-3)
