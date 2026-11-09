from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.budget import budget, day, grazing, lasts, rates, show, trip
from terrarium.config import DEFAULT

BASE = load(DEFAULT)
# hand numbers: drain 0.01 and move 0.02 a second, food 0.4, a crop of 2 slowing the walk home by 0.3, top speed 2
CFG = replace(BASE,
              energy=replace(BASE.energy, start=0.6, drain=0.01, move=0.02, food=0.4),
              creature=replace(BASE.creature, max_speed=2.0),
              crop=replace(BASE.crop, capacity=2, slow=0.15),
              night=replace(BASE.night, cycle=0.0),
              young=replace(BASE.young, seconds=0.0),
              jump=replace(BASE.jump, height=0.0, energy=0.0))


def test_full_thrust_lasts_one_over_drain_plus_move():
    r = rates(CFG)
    assert r['full thrust']['day'] == pytest.approx(0.03)
    assert lasts(1.0, r['full thrust']['day']) == pytest.approx(1 / 0.03)
    assert lasts(0.6, r['resting']['day']) == pytest.approx(60)


def test_the_young_pay_their_share_and_the_cold_has_its_own_columns():
    cold = replace(CFG, night=replace(CFG.night, cycle=120.0, length=60.0, cold=0.02, nest=0.5))
    r = rates(cold, share=0.5)
    assert r['resting']['day'] == pytest.approx(0.005)
    assert r['resting']['dark out'] == pytest.approx((0.01 + 0.02) * 0.5)
    assert r['resting']['dark nest'] == pytest.approx((0.01 + 0.01) * 0.5)


def test_a_trip_walks_out_at_full_speed_and_back_slowed_by_the_crop():
    t = trip(CFG, 7.0)
    # 7 m at 2 m/s out, 7 m at 1.4 m/s back
    assert t['secs'] == pytest.approx(3.5 + 5.0)
    assert t['walking'] == pytest.approx(0.02 * 8.5)
    assert t['cost'] == pytest.approx(0.03 * 8.5)
    assert t['home'] == pytest.approx(0.8)
    assert t['return'] == pytest.approx(0.8 / (0.03 * 8.5))


def test_a_tree_trip_pays_for_the_jump_and_the_young_for_less_of_everything():
    tree = replace(CFG, jump=replace(CFG.jump, height=0.8, energy=0.01), tree=replace(CFG.tree, points=1.0, reach=0.5),
                   young=replace(CFG.young, seconds=60.0, speed=0.5, energy=0.1))
    assert trip(tree, 7.0)['hop'] == pytest.approx(0.01)
    kid = trip(tree, 7.0, young=True)
    # out at 1 m/s and back at 0.7
    assert kid['secs'] == pytest.approx(7 + 10)
    assert kid['cost'] == pytest.approx(0.03 * 17 * 0.1 + 0.01 * 0.1)


def test_the_printed_world_agrees_with_its_own_arithmetic():
    b = budget(CFG, arenas=4)
    for per in ('any', 'nearest'):
        p50, p90 = b['food'][per]['adult']
        assert p50['dist'] <= p90['dist'] and p50['cost'] <= p90['cost']
        assert p50['cost'] == pytest.approx(trip(CFG, p50['dist'])['cost'])
    assert b['food']['nearest']['adult'][0]['dist'] <= b['food']['any']['adult'][0]['dist']
    assert 'young' not in b['groups'] and 'pond' not in b
    assert 'return, food / cost' in show(CFG, b)


def test_a_day_solves_the_food_share_with_the_pond_walking_in_it():
    # 10 s food trips bringing 0.8: k = 12.5 s a bar, food share = 12.5 × 0.01 / (1 − 12.5 × 0.02) = 1/6
    dry = day(CFG, 10.0, None)
    assert dry['food trips'] == pytest.approx(1 / 6)
    assert dry['left'] == pytest.approx(5 / 6)
    # water 0.01 a second, 0.7 a 3.5 s pond trip, drinking 0.26 net
    wet = replace(CFG, water=replace(CFG.water, ponds=1, radius=1.5, distance=5.0, drain=0.01, drink=0.27))
    d = day(wet, 10.0, 3.5)
    assert d['pond trips'] == pytest.approx(0.05)
    assert d['drinking'] == pytest.approx(0.01 / 0.26)
    assert d['food trips'] == pytest.approx(12.5 * (0.01 + 0.02 * 0.05) / 0.75)


def test_grass_gives_bite_times_food_a_second_and_a_meadow_what_its_cells_grow_back():
    cfg = replace(CFG, grass=replace(CFG.grass, cell=0.5, meadows=2, radius=1.0, distance=2.0, base=0.0, regrow=0.02,
                                     bite=0.25, food=0.4))
    g = grazing(cfg)
    assert g['rate'] == pytest.approx(0.1) and g['net'] == pytest.approx(0.09)
    assert g['cell lasts'] == pytest.approx(4) and g['regrow'] == pytest.approx(50)
    # two meadows of pi / 0.25 cells each, each growing back 0.02 a second worth 0.4 a unit
    assert g['cells'] == pytest.approx(8 * np.pi) and g['steady'] == pytest.approx(8 * np.pi * 0.02 * 0.4)
    assert g['share of time'] == pytest.approx(0.1)
    # the young eat the same energy off a smaller share of the cover
    assert grazing(cfg, 0.25)['cell lasts'] == pytest.approx(16)


def test_a_world_with_only_grass_prints_without_a_food_trip():
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=1), food=replace(CFG.food, count=0), crop=replace(CFG.crop, capacity=0),
                  grass=replace(CFG.grass, meadows=1, radius=1.0, distance=4.0, regrow=0.02, bite=0.25, food=0.4))
    b = budget(cfg, arenas=4)
    assert b['meadow']['p50'] == pytest.approx(4.0) and 'day' not in b
    text = show(cfg, b)
    assert 'a full cell lasts one nim' in text and 'no food but the grass' in text
