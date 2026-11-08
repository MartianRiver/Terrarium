from dataclasses import fields, replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, load_train
from terrarium.forage import Forage
from terrarium.random_actions import RandomActions
from terrarium.schema import ACTIONS

CFG = load(DEFAULT)


def meal(energy: float) -> float:
    """The reward for one tick standing on a berry at this energy, paid by needs alone."""
    train = load_train()
    paid = replace(train, reward=replace(train.reward, food=0.0, home=0.0, colony=0.0, needs=1.0))
    env = Forage(CFG, paid, 1, 0)
    w = env.world
    w.energy[:] = energy
    w.food_present[0, 0] = True
    w.food_pos[0, 0] = w.pos[0, 0]
    _, reward, *_ = env.step(np.zeros((env.samples, 5)))
    return float(reward[0])


def test_a_meal_pays_more_the_hungrier_it_finds_you():
    food = CFG.energy.food
    # hunger 0.7 → 0.3, minus a tick's drain
    assert meal(0.3) == pytest.approx(0.7**2 - (0.7 - food)**2, rel=0.01)
    assert meal(0.3) > meal(1 - food) > 0


def test_a_full_one_gets_nothing():
    assert meal(1.0) == 0


COLONY = load(DEFAULT.parent / 'colony.toml')
YOUNG = load(DEFAULT.parent / 'colony-young.toml')
EAT = ACTIONS.index('eat')


def paid(needs, food=0.0):
    train = load_train()
    zero = {f.name: 0.0 for f in fields(train.reward)}
    return replace(train, reward=replace(train.reward, **{**zero, 'needs': needs, 'food': food}))


def store_meal(cfg, energy, needs=1.0, young=False, store=5.0):
    """Creature 0 at home, empty-cropped, eats from the store once; returns the env and its reward."""
    env = Forage(cfg, paid(needs), 1, 0)
    w = env.world
    body = w.physics.bodies[0][0]
    body.position, body.velocity = tuple(w.nests[0]), (0, 0)
    w.physics.read()
    w.energy[0, 0] = energy
    w.crop[0, 0] = 0
    w.store[0, 0] = store
    if young:
        w.young[0, 0] = 1000
    act = np.full((env.samples, len(ACTIONS)), -1.0)
    act[0, EAT] = 1.0
    _, reward, *_ = env.step(act)
    return env, float(reward[0])


def test_a_meal_from_the_store_counts():
    # 0.5 → 0.9 (a jelly gives 0.4): 0.4 × (2 × 0.1 + 0.4), less a tick's drain on the hunger left
    env, reward = store_meal(COLONY, 0.5)
    assert env.world.jelly[0, 0] == 1 and env.world.fed[0, 0] == 0
    assert reward == pytest.approx(0.24, abs=0.01)
    assert store_meal(COLONY, 0.5, needs=0.0)[1] == 0


def test_a_full_one_gets_nothing_from_the_store():
    env, reward = store_meal(COLONY, 1.0)
    assert env.world.store[0, 0] == 5 and reward == 0


def test_a_jelly_that_overfills_pays_only_what_stayed():
    # from 0.8 a jelly of 0.9 would reach 1.7; only the 0.2 that fits counts
    cfg = replace(COLONY, jelly=replace(COLONY.jelly, energy=0.9, hunger=0.9))
    env, _ = store_meal(cfg, 0.8)
    assert env.world.nourished[0, 0] == pytest.approx(0.2, abs=0.01)


def test_a_young_bite_pays_its_fraction():
    # a young one at 0.8 takes a bite of 0.25 jelly to fill up (0.2 energy); a store with half a bite left gives half
    env, _ = store_meal(YOUNG, 0.8, young=True)
    assert env.world.nourished[0, 0] == pytest.approx(0.2, abs=0.01)
    env, _ = store_meal(YOUNG, 0.8, young=True, store=0.125)
    assert env.world.nourished[0, 0] == pytest.approx(0.1, abs=0.01)


def test_nourished_is_fed_until_something_eats_from_the_store():
    env = Forage(COLONY, paid(1.0, food=1.0), 2, 3)
    w = env.world
    w.energy[:] = 0.3
    w.store[:] = 20
    acts = RandomActions(2, len(w.colony), 3)
    rng = np.random.default_rng(1)
    for _ in range(200 // env.repeat):
        a = np.full((env.samples, len(ACTIONS)), -1.0)
        a[:, :2] = acts().reshape(-1, 2)
        a[:, EAT] = rng.choice([-1.0, 1.0], env.samples)
        env.step(a)
        # whatever came from the store is the only gap between the two
        assert (w.nourished >= w.fed - 1e-9).all()
        assert np.allclose((w.nourished - w.fed)[w.jelly == 0], 0)
    assert w.jelly.sum() > 0


def lost_env(needs, needs_lost, cfg=CFG):
    train = load_train()
    zero = {f.name: 0.0 for f in fields(train.reward)}
    return Forage(cfg, replace(train, reward=replace(train.reward, **zero | {'needs': needs, 'needs_lost': needs_lost})), 1, 0)


def step_at(env, energy):
    w = env.world
    w.energy[:] = energy
    _, reward, *_ = env.step(np.zeros((env.samples, len(ACTIONS))))
    return reward


def test_a_tick_of_drain_is_charged_its_hunger_squared():
    env = lost_env(0.0, 1.0)
    reward = step_at(env, 0.6)
    after = env.world.energy[0, 0]
    assert after < 0.6
    assert reward[0] == pytest.approx((1 - 0.6)**2 - (1 - after)**2) and reward[0] < 0


def test_needs_lost_off_leaves_a_meal_as_it_was():
    for energy in (0.3, 0.7):
        a, b = lost_env(1.0, 0.0), lost_env(1.0, 1.0)
        for env in (a, b):
            env.world.food_present[0, 0] = True
            env.world.food_pos[0, 0] = env.world.pos[0, 0]
        assert step_at(a, energy)[0] == meal(energy)
        # with both on, the meal's tick is the whole change: a rise in energy is a fall in hunger squared
        reward = step_at(b, energy)
        assert reward[0] == pytest.approx((1 - energy)**2 - (1 - b.world.energy[0, 0])**2)


def test_both_halves_make_the_whole_change_in_hunger_squared():
    env = lost_env(1.0, 1.0)
    w = env.world
    w.food_present[0, 0] = True
    w.food_pos[0, 0] = w.pos[0, 0]
    reward = step_at(env, 0.4)
    assert w.fed[0, 0] > 0
    assert reward[0] == pytest.approx(0.6**2 - (1 - w.energy[0, 0])**2)


def test_a_death_pays_nothing_from_needs_lost():
    env = lost_env(0.0, 1.0)
    env.world.energy[:] = 0.6
    env.world.energy[0, 0] = 1e-9
    _, reward, *_ = env.step(np.zeros((env.samples, len(ACTIONS))))
    assert not env.world.alive[0, 0] and reward[0] == 0
    assert reward[1] < 0


def test_a_tick_that_ends_the_arena_pays_nothing_from_needs_lost():
    env = lost_env(0.0, 1.0)
    env.world.age[:] = env.world.episode_ticks - env.repeat
    reward = step_at(env, 0.6)
    assert (reward == 0).all()


def test_needs_lost_zero_is_bit_identical_over_a_rollout():
    keys = {f.name: 1.0 for f in fields(load_train().reward)}
    def run(**extra):
        train = load_train()
        env = Forage(COLONY, replace(train, reward=replace(train.reward, **keys | extra)), 2, 5)
        acts = RandomActions(2, len(env.world.colony), 5)
        out = []
        for _ in range(60):
            a = np.full((env.samples, len(ACTIONS)), -1.0)
            a[:, :2] = acts().reshape(-1, 2)
            out.append(env.step(a)[1].copy())
        return np.stack(out)
    base = run(needs_lost=0.0)
    assert np.array_equal(base, run(needs_lost=0.0))
    assert not np.array_equal(base, run(needs_lost=1.0))
