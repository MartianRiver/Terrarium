from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.schema import SELF
from terrarium.config import DEFAULT, Config, build, load_train, upgrade
from terrarium.forage import Forage, observe
from terrarium.world import World

CFG = load(DEFAULT)
NIGHT = load(DEFAULT.parent / 'night.toml')
SPRINT = NIGHT.sprint


def alone(cfg=NIGHT):
    cfg = replace(cfg, colonies=replace(cfg.colonies, count=1, size=1), block=())
    world = World(cfg)
    world.heading[:] = -np.pi / 2  # facing open ground, away from the nest
    # no food anywhere, so nothing gets eaten and slows it down
    world.food_regrow[:] = 10**9
    # midday, so the cold of the dawn doesn't count
    world.clock[:] = 30.0
    return world


def spend(world, action, ticks):
    before = world.energy[0, 0]
    for _ in range(ticks):
        world.step(np.array([[action]], float))
    return before - world.energy[0, 0]


def test_turning_costs_by_its_square():
    hz, e = NIGHT.tick_hz, NIGHT.energy
    full, half, none = (spend(alone(), [0.0, t], hz) for t in (1.0, 0.5, 0.0))
    assert none == pytest.approx(e.drain)
    assert full - none == pytest.approx(e.turn) and half - none == pytest.approx(e.turn / 4)


def test_a_sprint_is_a_burst_then_a_rest():
    world = alone()
    hz, burst, rest = NIGHT.tick_hz, round(SPRINT.seconds * NIGHT.tick_hz), round(SPRINT.cooldown * NIGHT.tick_hz)
    for _ in range(hz):
        world.step(np.array([[[1.0, 0.0, -1, -1, -1]]]))
    walking = np.hypot(*world.vel[0, 0])
    # asking once is enough: the burst runs its length, faster and dearer
    world.step(np.array([[[1.0, 0.0, -1, -1, 1]]]))
    used = spend(world, [1.0, 0.0, -1, -1, -1], burst - 1) / (burst - 1)
    assert np.hypot(*world.vel[0, 0]) == pytest.approx(walking * SPRINT.speed, rel=0.02)
    e = NIGHT.energy
    assert used * hz == pytest.approx(e.drain + e.move + SPRINT.energy)
    assert world.sprinting[0, 0] == 0 and world.resting[0, 0] == rest
    # no second burst until the rest is over
    for _ in range(rest - 1):
        world.step(np.array([[[1.0, 0.0, -1, -1, 1]]]))
        assert world.sprinting[0, 0] == 0
    world.step(np.array([[[1.0, 0.0, -1, -1, 1]]]))
    world.step(np.array([[[1.0, 0.0, -1, -1, 1]]]))
    assert world.sprinting[0, 0] == burst - 1


def test_sprint_does_nothing_when_off():
    world = alone(CFG)
    assert not CFG.sprint.on
    world.step(np.array([[[1.0, 0.0, -1, -1, 1]]]))
    assert world.sprinting[0, 0] == 0 and world.spent[0, 0] == pytest.approx(CFG.energy.move * CFG.dt)


def test_the_brain_feels_its_sprint():
    world = alone()
    world.step(np.array([[[1.0, 0.0, -1, -1, 1]]]))
    me = observe(world, np.zeros((1, 1, 2))).me[0]
    sprinting, rested = me[SELF.index('sprinting')], me[SELF.index('rested')]
    assert sprinting == pytest.approx(1 - 1 / round(SPRINT.seconds * NIGHT.tick_hz)) and rested == 0
    assert observe(alone(), np.zeros((1, 1, 2))).me[0, SELF.index('rested')] == 1


def test_effort_is_charged_in_food_s_worth():
    train = load_train()
    paid = replace(train, reward=replace(train.reward, food=0.0, home=0.0, colony=0.0, effort=1.0))
    env = Forage(NIGHT, paid, 1, 0)
    env.world.food_regrow[:] = 1
    actions = np.zeros((env.samples, 5))
    actions[:, :2] = 1.0
    _, reward, *_ = env.step(actions)
    e = NIGHT.energy
    assert reward == pytest.approx(-(e.move + e.turn) * NIGHT.dt / e.food, rel=1e-4)


def test_old_run_records_load_without_turning_costs_or_sprint():
    recorded = CFG.to_dict()
    del recorded['sprint'], recorded['energy']['turn']
    old = build(Config, upgrade(recorded))
    assert old.energy.turn == 0 and not old.sprint.on and old.energy.move == CFG.energy.move
