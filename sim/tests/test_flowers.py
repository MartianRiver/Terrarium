from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, Config, build, upgrade
from terrarium.forage import observe
from terrarium.replay import frame
from terrarium.schema import ACTIONS, SELF
from terrarium.vision import FLOWER, look
from terrarium.world import World

CFG = load(DEFAULT)
COLONY = load(DEFAULT.parent / 'colony.toml')
FL = COLONY.flowers
HZ = COLONY.tick_hz


def alone(cfg=COLONY):
    cfg = replace(cfg, colonies=replace(cfg.colonies, count=1, size=1, room=0), block=())
    world = World(cfg)
    world.heading[:] = -np.pi / 2  # facing open ground, away from the nest
    world.food_regrow[:] = 10**9
    # midday
    world.clock[:] = 30.0
    return world


def still(world, ticks=1, action=(0.0, 0.0)):
    for _ in range(ticks):
        world.step(np.array([[action]], float))


def open_on(world, at):
    world.flower_pos[0, 0] = at
    world.flower_left[0, 0] = round(FL.open * HZ)
    world.flower_due[:] = 10**9


def test_a_flower_opens_by_day_and_closes_after_a_while():
    world = alone()
    world.flower_due[:] = 1
    still(world)
    assert world.flowers_open[0, 0]
    first = world.flower_id[0, 0]
    assert first not in world.food_id[0] and first not in world.creature_id[0]
    # clear of the nest
    gap = np.hypot(*(world.flower_pos[0, 0] - world.nests[0]))
    assert gap > COLONY.colonies.nest_radius + COLONY.food.clearance
    world.flower_due[:] = 10**9
    still(world, round(FL.open * HZ) - 1)
    assert world.flowers_open[0, 0]
    still(world)
    assert not world.flowers_open.any()


def test_nightfall_closes_them_and_none_open_in_the_dark():
    world = alone()
    world.clock[:] = COLONY.night.cycle - COLONY.night.length - 0.1
    open_on(world, (5.0, 5.0))
    still(world, 3)
    assert world.dark[0] and not world.flowers_open.any()
    world.flower_due[:] = 1
    still(world, HZ)
    assert not world.flowers_open.any() and world.flower_due[0] == 1


def test_the_first_to_touch_one_drinks_it_all():
    world = alone()
    world.energy[0, 0] = 0.1
    open_on(world, world.pos[0, 0])
    still(world)
    assert not world.flowers_open.any() and world.drunk[0, 0] == 1
    # eaten while hungry, the rest carried
    e = COLONY.energy
    assert world.energy[0, 0] == pytest.approx(0.1 + 2 * e.food - e.drain * COLONY.dt, abs=1e-3)
    assert world.crop[0, 0] == FL.food - 2 and world.fed[0, 0] == pytest.approx(2 * e.food)
    assert world.nectar[0, 0] == round(FL.boost * HZ)
    me = observe(world, np.zeros((1, 1, 2))).me
    assert me[0, SELF.index('nectar')] == pytest.approx(1.0)


def test_nectar_makes_it_faster_for_a_while():
    world = alone()
    still(world, HZ, (1.0, 0.0))
    walking = np.hypot(*world.vel[0, 0])
    world.nectar[0, 0] = round(FL.boost * HZ)
    still(world, HZ, (1.0, 0.0))
    assert np.hypot(*world.vel[0, 0]) == pytest.approx(walking * FL.speed, rel=0.02)
    still(world, round((FL.boost - 1) * HZ), (0.0, 0.0))
    assert world.nectar[0, 0] == 0
    still(world, HZ, (1.0, 0.0))
    assert np.hypot(*world.vel[0, 0]) == pytest.approx(walking, rel=0.02)


def test_a_flower_is_seen_as_its_own_kind():
    world = alone()
    open_on(world, world.pos[0, 0] + (0.0, -2.0))
    assert (look(world).kind[0, 0] == FLOWER).any()
    world.flower_left[:] = 0
    assert not (look(world).kind[0, 0] == FLOWER).any()


def test_replays_show_flowers_and_who_is_on_nectar():
    world = alone()
    open_on(world, (5.0, 5.0))
    world.nectar[0, 0] = 2 * HZ
    out = frame(world, 0)
    assert out['flowers'] == [{'id': int(world.flower_id[0, 0]), 'x': 5.0, 'y': 5.0}]
    assert out['creatures'][0]['nectar'] == 2.0 and out['creatures'][0]['sprinting'] == 0
    assert 'flowers' not in frame(World(CFG), 0)


def test_none_open_with_flowers_off():
    assert not CFG.flowers.on
    world = World(CFG, 2, seed=3)
    for _ in range(40):
        world.step(np.zeros((2, len(world.colony), 6)))
    assert world.flower_pos.shape[1] == 0 and not world.nectar.any()


def test_old_run_records_load_without_flowers():
    recorded = COLONY.to_dict()
    del recorded['flowers']
    assert not build(Config, upgrade(recorded)).flowers.on


SPOTS = load(DEFAULT.parent / 'spots.toml')


def test_with_spots_they_open_only_there_and_the_spots_stay_apart():
    world = World(SPOTS, 8, seed=1)
    fl = SPOTS.flowers
    for a in range(8):
        assert np.hypot(*(world.flower_spots[a, 0] - world.flower_spots[a, 1])) >= fl.spot_gap
    opened = []
    for _ in range(round(60 * HZ)):
        before = world.flowers_open.copy()
        world.step(np.zeros((8, len(world.colony), len(ACTIONS))))
        opened += [(a, world.flower_pos[a, f].copy()) for a, f in zip(*np.nonzero(world.flowers_open & ~before))]
    assert len(opened) > 8
    for a, p in opened:
        assert np.isclose(np.hypot(*(world.flower_spots[a] - p).T), 0).any()


def test_spots_are_drawn_anew_each_episode():
    world = World(SPOTS, 2, seed=2)
    first = world.flower_spots.copy()
    world.reset(np.array([True, False]))
    assert not np.allclose(world.flower_spots[0], first[0]) and np.allclose(world.flower_spots[1], first[1])


def test_old_run_records_have_flowers_anywhere():
    recorded = COLONY.to_dict()
    for key in ('spots', 'spot_gap'):
        del recorded['flowers'][key]
    assert build(Config, upgrade(recorded)).flowers.spots == 0
