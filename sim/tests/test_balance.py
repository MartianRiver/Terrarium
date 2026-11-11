import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

BENCH = Path(__file__).parent.parent / 'bench'
sys.path.insert(0, str(BENCH))

import balance  # noqa: E402
import balance_supply as supply  # noqa: E402
from terrarium import load  # noqa: E402

WORLD = load(BENCH / 'worlds' / 'ab-2x9.toml')


def test_the_supply_ratio_by_hand():
    # 18 nims x (0.01 x 120 s + 0.02 x half of 60 s) / 0.4 = 81 foods; 22 places x 60 s / 9 s = 146.7
    assert supply.need(WORLD) == pytest.approx(81)
    assert supply.food_grown(WORLD) == pytest.approx(22 * 60 / 9)
    assert supply.ratio(WORLD) == pytest.approx(146.67 / 81, rel=1e-3)


@pytest.mark.parametrize('target', [1.5, 1.0, 0.8])
def test_fitting_food_count_lands_near_the_target(target):
    fitted = supply.fit(WORLD, target, 'count')
    # a whole number of foods: within half a food of the target
    assert abs(supply.ratio(fitted) - target) < 0.5 * 60 / 9 / supply.need(WORLD) + 1e-9
    assert fitted.food.regrow_min == WORLD.food.regrow_min


@pytest.mark.parametrize('target', [1.5, 0.8])
def test_fitting_regrow_is_exact_and_keeps_the_count(target):
    fitted = supply.fit(WORLD, target, 'regrow')
    assert supply.ratio(fitted) == pytest.approx(target)
    assert fitted.food.count == WORLD.food.count
    assert fitted.food.regrow_max / fitted.food.regrow_min == pytest.approx(WORLD.food.regrow_max / WORLD.food.regrow_min)


def test_grass_counts_toward_supply_and_the_fit_leaves_it_alone():
    grass = replace(WORLD, grass=replace(WORLD.grass, meadows=2, radius=1.0, regrow=0.02, food=0.4, bite=0.25))
    # two meadows of ~12.6 cells, each cell regrowing 0.02 x 120 s of cover worth 0.4 / 0.4 foods
    assert supply.grass_foods(grass) == pytest.approx(2 * np.pi * 1.0 ** 2 / 0.25 * 0.02 * 120)
    fitted = supply.fit(grass, 1.0)
    assert supply.ratio(fitted) == pytest.approx(1.0, abs=0.05)
    assert fitted.food.count < supply.fit(WORLD, 1.0).food.count
    with pytest.raises(ValueError):
        supply.fit(grass, 0.1)


def test_a_long_run_never_resets_and_the_dead_stay_counted():
    cfg = replace(WORLD, colonies=replace(WORLD.colonies, size=3, room=1))
    cycle = supply.cycle_length(cfg)
    run = balance.simulate(cfg, 'carrier', seeds=2, cycles=2.5, every=30.0, seed=7)
    t = np.array(run['t'])
    # sampled through two and a half cycles, past where a 360 s episode would have been over and restarted
    assert t[-1] == 2.5 * cycle
    deaths = np.array(run['deaths']).sum(-1)
    assert (np.diff(deaths, axis=0) >= 0).all()
    alive = np.array(run['alive']).sum(-1)
    births = np.array(run['births']).sum(-1)
    # everyone who ever lived is alive, or counted dead: no one is reset into the colony
    assert (alive[-1] == 6 + births[-1] - deaths[-1]).all()


def test_gates_judge_rich_and_lean_runs():
    t = list(np.arange(0, 1201, 120.0))                        # 10 cycles, one sample a cycle
    run = lambda totals: {'t': t, 'alive': [[[x // 2, x - x // 2]] * 2 for x in totals]}
    steady = gates_of(run([18] * 11), 'rich')
    assert steady['pass'] and steady['late_slope'] == 0
    sinking = gates_of(run([18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8]), 'rich')
    assert not sinking['checks']['keeps 90% of the start'] and not sinking['checks']['no late decline']
    # lean: down to 70% by day three and then flat is balanced; still falling at the end is not
    leveled = gates_of(run([18, 16, 14, 13, 13, 13, 13, 13, 13, 13, 13]), 'lean')
    assert leveled['pass']
    falling = gates_of(run([18, 17, 16, 15, 14, 13, 12, 11, 10, 10, 10]), 'lean')
    assert not falling['checks']['no late decline']


def gates_of(run, kind):
    return balance.gates(run, 18, kind, 120.0)


def test_a_colony_dying_out_is_not_hidden_by_the_one_that_carries_the_arena():
    t = list(np.arange(0, 1201, 120.0))
    # two games, two colonies: colony 1 of the second game is gone after day two, the arena never empties
    alive = [[[[9, 9], [9, 9 if i < 3 else 0]]] [0] for i in range(11)]
    run = {'t': t, 'alive': alive}
    g = gates_of(run, 'rich')
    assert g['extinct_games'] == 0 and g['extinct_colonies'] == 1
    assert not g['checks']['no colony goes extinct'] and g['pass'] is False and g['status'] == 'fail'
    # the old arena total alone would have passed this far
    assert g['checks']['no game goes extinct']


def test_a_rich_world_has_to_hold_every_day_not_only_the_last():
    t = list(np.arange(0, 1201, 120.0))
    dip = [18, 18, 10, 10, 18, 18, 18, 18, 18, 18, 18]
    g = gates_of({'t': t, 'alive': [[[x // 2, x - x // 2]] * 2 for x in dip]}, 'rich')
    assert g['checks']['keeps 90% of the start'] and not g['checks']['keeps 90% of the start every day']
    assert g['status'] == 'fail'


def test_a_run_too_short_to_judge_is_incomplete_not_a_pass():
    t = list(np.arange(0, 241, 120.0))
    g = gates_of({'t': t, 'alive': [[[9, 9]] * 2] * 3}, 'rich')
    assert g['status'] == 'incomplete' and g['pass'] is None and all(g['checks'].values())


def test_a_long_enough_steady_run_passes_with_its_days_listed():
    t = list(np.arange(0, 1201, 120.0))
    g = gates_of({'t': t, 'alive': [[[9, 9]] * 2] * 11}, 'rich')
    assert g['status'] == 'pass' and len(g['daily_median']) == 10 and g['extinct_colonies'] == 0
