from dataclasses import replace

import numpy as np

from terrarium import World, load
from terrarium.evals import POLICIES, run
from terrarium.world import EMPTY

CFG = load()
ARENAS = 200
LAST = CFG.colonies.count * (CFG.colonies.size + CFG.colonies.room) - 1


def stack(world, spot=(0.0, 0.0)):
    """The first creature and the last, rivals, on one spot in every arena."""
    for a in range(world.arenas):
        for i in (0, LAST):
            body = world.physics.bodies[a][i]
            body.position, body.velocity = spot, (0, 0)
    world.physics.read()
    assert world.colony[0] != world.colony[LAST]


def still(world):
    return np.zeros((world.arenas, len(world.colony), 2))


def eaten_in_a_tie(arenas, seed):
    world = World(CFG, arenas, seed)
    stack(world)
    world.food_pos[:, 0] = 0.0
    world.food_regrow[:] = EMPTY
    world.food_regrow[:, 0] = 0
    world.energy[:] = 0.5
    world.step(still(world))
    assert (world.meals.sum(1) == 1).all()
    return world.meals[:, 0]


def fair(wins):
    # 200 coin flips: 70 to 130 is more than four standard deviations either side
    assert 70 < wins.sum() < 130


def test_a_tie_for_food_goes_to_either_colony():
    fair(eaten_in_a_tie(ARENAS, 5))


def test_a_tie_for_a_flower_goes_to_either_colony():
    cfg = replace(CFG, flowers=replace(CFG.flowers, count=1, every_min=100.0, every_max=100.0, open=30.0, radius=0.3))
    world = World(cfg, ARENAS, 9)
    stack(world)
    world.flower_left[:, 0] = 100
    world.flower_pos[:, 0] = 0.0
    world.food_regrow[:] = EMPTY
    world.step(still(world))
    assert (world.drunk[:, 0] + world.drunk[:, LAST] == 1).all()
    fair(world.drunk[:, 0])


def test_a_tie_for_a_berry_goes_to_either_colony():
    cfg = replace(CFG, carry=replace(CFG.carry, reach=0.3))
    world = World(cfg, ARENAS, 11)
    stack(world)
    world.food_pos[:, 0] = 0.0
    world.food_regrow[:] = EMPTY
    world.food_regrow[:, 0] = 0
    want = np.zeros(world.alive.shape, bool)
    want[:, [0, LAST]] = True
    world._carry(want)
    got = world.load[:, [0, LAST]] >= 0
    assert (got.sum(1) == 1).all()
    fair(got[:, 0])


def test_standing_in_two_nests_is_a_random_one_of_them():
    cfg = replace(CFG, colonies=replace(CFG.colonies, nest_radius=8.0))
    world = World(cfg, 50, 13)
    mid = world.nests[:2].mean(0)
    assert (np.hypot(*(world.nests[:2] - mid).T) < cfg.colonies.nest_radius).all()
    world.pos[:, 0] = mid
    first = world.nest_at()[:, 0]
    assert set(first) <= {0, 1} and (first == world.nest_at()[:, 0]).all()
    assert 10 < (first == 0).sum() < 40


def test_the_same_seed_plays_the_same_tie():
    a = eaten_in_a_tie(40, 3)
    assert (a == eaten_in_a_tie(40, 3)).all()
    assert (a != eaten_in_a_tie(40, 4)).any()


def test_a_game_is_the_same_in_a_bigger_job():
    assert (eaten_in_a_tie(10, 7) == eaten_in_a_tie(60, 7)[:10]).all()


def test_a_world_with_no_ties_plays_as_it_did():
    # numbers taken before the tie stream existed: one nim, so nothing is ever tied for
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=1), episode=replace(CFG.episode, seconds=60.0))
    greedy, random = (run(cfg, POLICIES[name], 6, 77) for name in ('greedy', 'random'))
    assert greedy['food_per_minute']['mean'] == 8.0 and greedy['food_per_minute']['p10'] == 6.5
    assert random['food_per_minute']['mean'] == 7 / 6 and random['seconds_alive']['mean'] == 52.80833333333334
