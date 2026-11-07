from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT, Block
from terrarium.replay import frame
from terrarium.schema import ACTIONS
from terrarium.vision import BLOCK, look
from terrarium.world import AWAY, World

COLONY = load(DEFAULT.parent / 'colony.toml')
CARRY = ACTIONS.index('carry')
YES, NO = 1.0, -1.0
# a door: too heavy to push, small enough to carry
DOOR = Block(x=0.0, y=0.0, angle=0.0, w=0.5, h=1.2, mass=1000.0, friction=0.6, carry=True, shut=0.0)


def world_with(*blocks):
    cfg = replace(COLONY, colonies=replace(COLONY.colonies, count=1, size=1, room=0), block=blocks)
    world = World(cfg)
    world.heading[:] = -np.pi / 2
    world.food_regrow[:] = 10**9
    world.flower_due[:] = 10**9
    world.clock[:] = 30.0
    # each block in a row ahead of it (-y), the first just within reach
    me = world.pos[0, 0]
    world.physics.shift([0], list(range(len(blocks))), np.array([me + (2.5 * k, -1.2) for k in range(len(blocks))]),
                        np.zeros(len(blocks)))
    return world


def step(world, carry, thrust=0.0, turn=0.0, ticks=1):
    for _ in range(ticks):
        act = np.full((1, 1, len(ACTIONS)), NO)
        act[..., 0], act[..., 1] = thrust, turn
        act[0, 0, CARRY] = carry
        world.step(act)


def test_a_heavy_block_wont_be_pushed_but_a_carryable_one_is_picked_up_and_put_down_in_front():
    world = world_with(DOOR)
    start = world.physics.block_pos[0, 0].copy()
    step(world, NO, thrust=1.0, ticks=40)
    assert np.hypot(*(world.physics.block_pos[0, 0] - start)) < 0.01
    step(world, YES)
    assert world.block_load[0, 0] == 0 and world.lifted[0, 0] == 1 and world.blocks_carried[0, 0]
    # off the ground: nothing sees it, and it rides on its carrier in replays
    assert (world.block_pos[0, 0] == AWAY).all()
    assert not (look(world).kind[0, 0] == BLOCK).any()
    shown = frame(world, 0)['blocks'][0]
    assert shown['carried'] == 1 and abs(shown['x'] - world.pos[0, 0, 0]) < 0.01
    # turn away and walk off with it, then set it down
    step(world, NO, turn=1.0, ticks=18)
    step(world, NO, thrust=1.0, ticks=20)
    step(world, YES)
    assert world.block_load[0, 0] == -1
    h = world.heading[0, 0]
    ahead = world.pos[0, 0] + (COLONY.creature.radius + DOOR.w / 2 + 0.05) * np.array([np.cos(h), np.sin(h)])
    assert np.hypot(*(world.physics.block_pos[0, 0] - ahead)) < 0.05
    assert np.hypot(*(world.block_pos[0, 0] - start)) > 1.0


def test_it_isnt_set_down_where_something_else_stands():
    world = world_with(DOOR, replace(DOOR, carry=False))
    step(world, YES)
    step(world, NO)
    assert world.block_load[0, 0] == 0
    # facing the other block, close enough that the door won't fit between
    world.physics.shift([0], [1], np.array([world.pos[0, 0] + (0.0, -1.0)]), np.zeros(1))
    step(world, YES)
    assert world.block_load[0, 0] == 0


def test_a_block_not_marked_carry_stays_put():
    world = world_with(replace(DOOR, carry=False))
    step(world, YES)
    assert world.block_load[0, 0] == -1 and world.lifted[0, 0] == 0


def test_one_that_dies_carrying_drops_it_and_a_new_episode_puts_it_back():
    world = world_with(DOOR)
    step(world, YES)
    world.energy[0, 0] = 1e-6
    step(world, NO)
    assert not world.alive[0, 0] and world.block_load[0, 0] == -1
    assert np.hypot(*(world.block_pos[0, 0] - world.pos[0, 0])) < 1.5
    world.reset(np.array([True]))
    assert (world.physics.block_pos[0, 0] == (DOOR.x, DOOR.y)).all() and world.block_load[0, 0] == -1


def test_a_door_that_swings_shut_goes_back_where_it_started_once_that_is_clear():
    door = replace(DOOR, x=3.0, y=3.0, shut=1.0)
    world = world_with(door, replace(DOOR, carry=False))
    step(world, YES)
    step(world, NO, turn=1.0, ticks=18)
    step(world, NO, thrust=1.0, ticks=20)
    step(world, YES)
    put = world.physics.block_pos[0, 0].copy()
    # something in its place keeps it waiting
    world.physics.shift([0], [1], np.array([[door.x, door.y]]), np.zeros(1))
    step(world, NO, ticks=round(door.shut * COLONY.tick_hz) + 5)
    assert np.allclose(world.physics.block_pos[0, 0], put) and world.shut_in[0, 0] == 0
    world.physics.shift([0], [1], np.array([[-3.0, 3.0]]), np.zeros(1))
    step(world, NO)
    assert np.allclose(world.physics.block_pos[0, 0], (door.x, door.y), atol=1e-6) and world.shut_in[0, 0] == -1


def test_a_door_picked_up_again_before_it_swings_shut_stays_with_its_carrier():
    door = replace(DOOR, x=3.0, y=3.0, shut=1.0)
    world = world_with(door)
    step(world, YES)
    step(world, NO, turn=1.0, ticks=18)
    step(world, NO, thrust=1.0, ticks=20)
    step(world, YES)
    step(world, NO, ticks=3)
    step(world, YES)
    step(world, NO, ticks=round(door.shut * COLONY.tick_hz) * 2)
    assert world.blocks_carried[0, 0] and world.shut_in[0, 0] == -1
