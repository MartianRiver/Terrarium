from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.forage import observe
from terrarium.replay import frame
from terrarium.schema import ACTIONS, SELF
from terrarium.vision import FOOD, look
from terrarium.world import CARRIED, World

COLONY = load(DEFAULT.parent / 'colony.toml')
CARRY = ACTIONS.index('carry')
YES, NO = 1.0, -1.0


def world_of(count=1, size=1, cfg=COLONY):
    cfg = replace(cfg, colonies=replace(cfg.colonies, count=count, size=size, room=0), block=())
    world = World(cfg)
    world.heading[:] = -np.pi / 2  # facing open ground, away from the nest
    world.food_regrow[:] = 10**9
    world.flower_due[:] = 10**9
    # midday
    world.clock[:] = 30.0
    return world


def berry(world, f, at):
    world.food_pos[0, f] = at
    world.food_regrow[0, f] = 0


def step(world, carry, thrust=0.0):
    n = len(world.colony)
    act = np.full((1, n, len(ACTIONS)), NO)
    act[..., 0], act[..., 1] = thrust, 0.0
    act[0, :, CARRY] = carry
    world.step(act)


def beside(world, i=0, gap=0.2):
    """A spot just within carry's reach of creature i, but out of reach for eating."""
    c = world.cfg
    return world.pos[0, i] + (c.creature.radius + c.food.radius + gap, 0.0)


def test_a_berry_is_picked_up_carried_and_put_down_still_a_berry():
    world = world_of()
    world.energy[:] = 1.0
    berry(world, 3, beside(world))
    step(world, YES)
    assert world.load[0, 0] == 3 and world.food_regrow[0, 3] == CARRIED and world.picked[0, 0] == 1
    # off the ground: not seen, and the crop has nothing to do with it
    assert not world.food_present[0, 3] and world.crop[0, 0] == 0
    # holding yes keeps it; only a fresh yes puts it down
    step(world, YES)
    assert world.load[0, 0] == 3
    for _ in range(20):
        step(world, NO, thrust=1.0)
    step(world, YES)
    assert world.load[0, 0] == -1 and world.food_present[0, 3] and world.food_by[0, 3] == 0
    # in front of it, where it walked to
    facing = np.array([np.cos(world.heading[0, 0]), np.sin(world.heading[0, 0])])
    assert np.dot(world.food_pos[0, 3] - world.pos[0, 0], facing) > 0


def test_out_of_reach_nothing_is_picked_up():
    world = world_of()
    berry(world, 0, beside(world, gap=world.cfg.carry.reach + 0.3))
    step(world, YES)
    assert world.load[0, 0] == -1 and world.food_present[0, 0]


def test_carrying_slows_it_and_costs_energy():
    a, b = world_of(), world_of()
    berry(a, 0, beside(a))
    step(a, YES)
    step(b, YES)
    assert a.load[0, 0] == 0 and b.load[0, 0] == -1
    a.energy[:] = b.energy[:] = 0.8
    for _ in range(60):
        step(a, NO, thrust=1.0)
        step(b, NO, thrust=1.0)
    assert a.energy[0, 0] < b.energy[0, 0]
    assert np.hypot(*a.vel[0, 0]) < np.hypot(*b.vel[0, 0])


def test_a_carried_berry_outlasts_nightfall():
    world = world_of()
    berry(world, 0, beside(world))
    step(world, YES)
    world.clock[:] = world.cfg.night.cycle - world.cfg.night.length - 0.05
    for _ in range(3):
        step(world, NO)
    assert world.dark[0] and world.load[0, 0] == 0
    step(world, YES)
    assert world.food_present[0, 0]


def test_one_that_dies_carrying_drops_it_where_it_falls():
    world = world_of()
    berry(world, 0, beside(world))
    step(world, YES)
    world.energy[:] = 1e-6
    step(world, NO)
    assert not world.alive[0, 0] and world.load[0, 0] == -1 and world.food_present[0, 0]


def test_a_nestmate_taking_a_put_down_berry_counts_to_whoever_put_it_there():
    world = world_of(size=2)
    world.physics.place([0], np.array([[(0.0, -6.0), (3.0, -6.0)]]))
    world.energy[:] = 1.0
    berry(world, 0, beside(world))
    step(world, YES)
    step(world, NO)
    step(world, YES)
    put = world.food_pos[0, 0].copy()
    assert world.food_by[0, 0] == 0
    # a hungry nestmate walks onto it
    world.energy[0, 1] = 0.3
    world.physics.place([0], np.array([[world.pos[0, 0], put]]))
    step(world, NO)
    assert world.given[0, 0] == 1 and world.given_hungry[0, 0] == 1
    assert world.food_by[0, 0] == -1 and world.given[0, 1] == 0


def test_the_brain_feels_the_load_and_sees_the_berry_again_once_down():
    world = world_of()
    berry(world, 0, beside(world, gap=0.0))
    world.heading[:] = 0.0
    step(world, YES)
    load = SELF.index('load')
    assert observe(world, np.zeros((1, 1, 2))).me[0, load] == 1
    assert not (look(world).kind == FOOD).any()
    step(world, NO)
    step(world, YES)
    assert observe(world, np.zeros((1, 1, 2))).me[0, load] == 0
    assert (look(world).kind == FOOD).any()


def test_replays_show_who_carries_and_the_berry_leaves_the_ground():
    world = world_of()
    berry(world, 0, beside(world))
    step(world, YES)
    f = frame(world, 0)
    assert f['creatures'][0]['load'] == 1
    assert not any(food['id'] == world.food_id[0, 0] for food in f['food'])


def test_with_carry_off_the_action_does_nothing():
    world = world_of(cfg=load(DEFAULT.parent / 'night.toml'))
    berry(world, 0, beside(world))
    step(world, YES)
    assert world.load[0, 0] == -1 and world.food_present[0, 0]
    assert 'load' not in frame(world, 0)['creatures'][0]
