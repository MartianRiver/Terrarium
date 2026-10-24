from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, Config, build, load_train, upgrade
from terrarium.forage import Forage
from terrarium.night import dark, light, warmth
from terrarium.world import World

CFG = load(DEFAULT)
# a 20 s day and its 10 s night, fading over 2 s
NIGHTS = replace(CFG, night=replace(CFG.night, cycle=30.0, length=10.0, dusk=2.0, cold=0.05))


def test_nights_are_off_unless_asked_for():
    assert not CFG.night.on
    assert (light(np.array([0.0, 25.0]), CFG.night) == 1).all() and not dark(np.array([25.0]), CFG.night).any()


def test_the_light_fades_at_dusk_and_comes_back_after_dawn():
    n = NIGHTS.night
    seconds = np.array([0.0, 1.0, 10.0, 19.0, 20.0, 25.0, 31.0])
    assert list(light(seconds, n)) == pytest.approx([0, 0.5, 1, 0.5, 0, 0, 0.5])
    assert list(dark(seconds, n)) == [False, False, False, False, True, True, False]


def test_the_food_standing_at_nightfall_goes_and_grows_back_after_dawn():
    w = World(NIGHTS, 2, 0)
    standing = []
    for _ in range(round(45 * CFG.tick_hz)):
        # standing still, so nothing gets eaten
        w.step(np.zeros((2, len(w.colony), 2)))
        standing.append(int(w.food_present[:, :w.wild].sum()))
    hz = CFG.tick_hz
    assert standing[round(19 * hz)] == 2 * CFG.food.count
    assert standing[round(20 * hz)] == 0 and standing[round(29.9 * hz)] == 0
    assert standing[round(44 * hz)] == 2 * CFG.food.count


def test_the_nest_and_nestmates_keep_the_cold_off():
    n = NIGHTS.night
    colony = np.array([0, 0, 0, 1])
    pos = np.array([[[0.0, 0.0], [1.0, 0.0], [10.0, 0.0], [0.5, 0.5]]])
    alive = np.ones((1, 4), bool)
    home = np.array([[False, False, False, True]])
    kept = warmth(pos, alive, colony, home, n)
    # the first two are close to each other, the third is alone, the fourth is close to both but not a nestmate
    assert list(kept[0]) == pytest.approx([n.huddle, n.huddle, 0, n.nest])
    alive[0, 1] = False
    assert warmth(pos, alive, colony, home, n)[0, 0] == 0


def test_the_cold_drains_faster_at_night():
    w = World(NIGHTS, 1, 0)
    # deep in the night, standing still on the spawn ring: outside the nest, nestmates spread round it
    w.age[:] = round(25 * CFG.tick_hz)
    before = w.energy.copy()
    w.step(np.zeros((1, len(w.colony), 2)))
    used = (before - w.energy)[0] * CFG.tick_hz
    kept = 1 - (used - CFG.energy.drain) / NIGHTS.night.cold
    assert used.max() > CFG.energy.drain
    assert np.allclose(kept, warmth(w.pos, w.alive, w.colony, w.nest_at() == w.colony, NIGHTS.night)[0], atol=1e-6)


def test_staggered_arenas_start_at_any_time_of_day():
    train = load_train()
    together = Forage(NIGHTS, train, 8, 0)
    assert (together.world.clock == 0).all()
    env = Forage(NIGHTS, replace(train, start=replace(train.start, staggered=True)), 8, 0)
    w = env.world
    assert len(np.unique(w.clock)) == 8 and (w.clock < NIGHTS.night.cycle).all()
    env.step(np.zeros((env.samples, 5)))
    standing = w.food_present[:, :w.wild].sum(1)
    assert (standing[w.dark] == 0).all() and (standing[~w.dark] == CFG.food.count).all()
    # an arena that starts over gets a new time of day
    before = w.clock.copy()
    w.age[0] = w.episode_ticks
    env.step(np.zeros((env.samples, 5)))
    assert w.clock[0] != before[0] and (w.clock[1:] == before[1:]).all()


def test_old_run_records_load_with_nights_off():
    recorded = CFG.to_dict()
    del recorded['night']
    old = build(Config, upgrade(recorded))
    assert not old.night.on and old.food == CFG.food


def test_being_warm_pays_by_the_second_and_more_in_the_dark():
    train = load_train()
    solo = replace(load(DEFAULT.parent / 'solo.toml'), night=NIGHTS.night)
    paid = replace(train, reward=replace(train.reward, food=0.0, home=0.0, snug=0.1, warm=1.0, colony=0.0))
    rewards = {}
    for clock in (5.0, 25.0):
        env = Forage(solo, paid, 2, 0)
        w = env.world
        w.clock[:] = clock
        # one at home, one well away from it
        w.physics.bodies[0][0].position = tuple(w.nests[0])
        w.physics.bodies[1][0].position = tuple(w.nests[0] + (8.0, 0.0))
        w.physics.read()
        _, reward, *_ = env.step(np.zeros((2, 5)))
        rewards[clock] = reward
    day, night_ = rewards[5.0], rewards[25.0]
    assert day[0] == pytest.approx(0.1 * solo.dt) and day[1] == 0
    assert night_[0] == pytest.approx(1.1 * solo.dt) and night_[1] == 0
