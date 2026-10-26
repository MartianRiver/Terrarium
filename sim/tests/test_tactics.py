from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.evals import POLICIES, run
from terrarium.tactics import REASONS, flower_in_view, reason
from terrarium.world import World

COLONY = load(DEFAULT.parent / 'colony.toml')
FLOWER, FOOD, HOME, ABOUT = range(4)


def out_alone():
    cfg = replace(COLONY, colonies=replace(COLONY.colonies, count=1, size=1, room=0), block=())
    world = World(cfg)
    world.clock[:] = 30.0
    world.food_regrow[:] = 10**9
    # 3 m east of the nest, facing further east
    world.pos[0, 0] = world.nests[0] + (3.0, 0.0)
    world.heading[:] = 0.0
    return world


def why(world, mine=0):
    return reason(world, world.nest_at(), np.full(world.alive.shape, mine))[0, 0]


def test_each_spot_gets_its_reason():
    world = out_alone()
    assert why(world) == ABOUT
    # facing home but with no need to be there
    world.heading[:] = np.pi
    assert why(world) == ABOUT
    world.energy[0, 0] = COLONY.jelly.hunger / 2
    assert why(world, mine=0) == ABOUT and why(world, mine=3) == HOME
    world.food_pos[0, 0], world.food_regrow[0, 0] = world.pos[0, 0] + (-1.0, 0.0), 0
    assert why(world, mine=3) == FOOD
    world.flower_pos[0, 0], world.flower_left[0, 0] = world.pos[0, 0] + (-2.0, 0.0), 10
    assert flower_in_view(world)[0, 0] and why(world, mine=3) == FLOWER
    world.pos[0, 0] = world.nests[0]
    assert why(world, mine=3) == -1


def test_sprints_are_put_down_to_why_they_started():
    # scripted players whose sprints are known, to check the counts against
    short = replace(COLONY, episode=replace(COLONY.episode, seconds=40.0),
                    flowers=replace(COLONY.flowers, every_min=1.0, every_max=2.0, count=4))

    def at_flowers(world):
        greedy = POLICIES['greedy'](world)
        return lambda w: np.concatenate([greedy(w), np.where(flower_in_view(w), 1.0, -1.0)[..., None]], -1)
    sp = run(short, at_flowers, 4)['sprints']
    assert sp['flower']['yes'] == 1 and sp['flower']['share'] == 1 and sp['per_minute_out'] > 0
    assert all(sp[r]['yes'] == 0 and sp[r]['share'] == 0 for r in REASONS[1:])

    def tossing(world):
        greedy, coin = POLICIES['greedy'](world), np.random.default_rng(0)
        return lambda w: np.concatenate([greedy(w), coin.choice([-1.0, 1.0], (*w.alive.shape, 1))], -1)
    r = run(short, tossing, 4)
    sp = r['sprints']
    assert sum(sp[k]['share'] for k in REASONS) == 1
    assert all(0.3 < sp[k]['yes'] < 0.7 for k in ('food', 'about'))
    # greedy heads for food, so a sprint that starts with food in view often ends in a meal
    assert sp['food']['paid'] > sp['about']['paid']
    fl = r['flower_use']
    assert fl['opened'] > 0 and 0 < fl['drunk'] <= 1 and fl['chased'] is not None
    assert r['nectar']['without'] > 0


def test_no_sprint_numbers_without_a_sprint():
    r = run(replace(COLONY, episode=replace(COLONY.episode, seconds=5.0)), POLICIES['greedy'], 2)
    assert all(r['sprints'][k]['share'] is None for k in REASONS) and r['sprints']['per_minute_out'] == 0
    world_cfg = load(DEFAULT)
    assert run(replace(world_cfg, episode=replace(world_cfg.episode, seconds=5.0)), POLICIES['greedy'], 2)['sprints'] is None
