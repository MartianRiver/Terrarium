from dataclasses import replace

import numpy as np
import pymunk
import pytest

from terrarium import World, load
from terrarium.random_actions import RandomActions
from terrarium.vision import BLOCK, CREATURE, FOOD, GAP, NOTHING, WALL, directions, look

CFG = load()
R = CFG.creature.radius
RANGE = CFG.vision.range


def alone(rays=1, blocks=()):
    """One creature at the centre facing +x, with a single ray straight ahead unless asked for more."""
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=1), block=blocks,
                  vision=replace(CFG.vision, rays=rays, fov=0.0 if rays == 1 else CFG.vision.fov))
    world = World(cfg)
    body = world.physics.bodies[0][0]
    body.position = (0, 0)
    world.physics.read()
    world.heading[:] = 0
    world.food_regrow[:] = 1
    return world


def seen(world):
    sight = look(world)
    return sight.dist, sight.kind


def two_colonies():
    """One creature in each of two colonies, one ray each: colony 0's nest is up the y axis, colony 1's down it."""
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=2, size=1), block=(),
                  vision=replace(CFG.vision, rays=1, fov=0.0))
    world = World(cfg)
    world.food_regrow[:] = 1
    return world


def place(world, *spots):
    for body, spot in zip(world.physics.bodies[0], spots):
        body.position = spot
    world.physics.read()


def test_food_ahead():
    world = alone()
    world.food_regrow[0, 0] = 0
    world.food_pos[0, 0] = (3.0, 0)
    dist, kind = seen(world)
    assert kind[0, 0, 0] == FOOD
    assert dist[0, 0, 0] == pytest.approx(3.0 - CFG.food.radius)


def test_eaten_food_is_not_seen():
    world = alone()
    world.food_pos[0, 0] = (3.0, 0)
    dist, kind = seen(world)
    assert kind[0, 0, 0] == NOTHING and dist[0, 0, 0] == RANGE


def test_wall_in_range_and_out():
    world = alone()
    world.physics.bodies[0][0].position = (CFG.arena.size / 2 - 2.0, 0)
    world.physics.read()
    dist, kind = seen(world)
    assert kind[0, 0, 0] == WALL and dist[0, 0, 0] == pytest.approx(2.0)
    world.heading[:] = np.pi
    dist, kind = seen(world)
    assert kind[0, 0, 0] == NOTHING and dist[0, 0, 0] == RANGE


def test_block_turned_and_nearest_wins():
    block = replace(CFG.block[0], x=4.0, y=0.0, angle=np.pi / 4)
    world = alone(blocks=(block,))
    world.food_regrow[0, 0] = 0
    world.food_pos[0, 0] = (6.0, 0)
    dist, kind = seen(world)
    # turned 45°, the box's near corner points straight back at the creature
    assert kind[0, 0, 0] == BLOCK
    assert dist[0, 0, 0] == pytest.approx(4.0 - block.w / np.sqrt(2))


def test_creatures_see_each_other_but_not_themselves():
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=2), block=(),
                  vision=replace(CFG.vision, rays=1, fov=0.0))
    world = World(cfg)
    world.food_regrow[:] = 1
    for body, x in zip(world.physics.bodies[0], (0.0, 2.0)):
        body.position = (x, 0)
    world.physics.read()
    world.heading[:] = [[0, np.pi]]
    dist, kind = seen(world)
    assert (kind[0, :, 0] == CREATURE).all()
    assert dist[0, :, 0] == pytest.approx(2.0 - R)
    assert look(world).nestmate.all()
    # the dead aren't there to see
    world.alive[0, 1] = False
    dist, kind = seen(world)
    assert kind[0, 0, 0] == NOTHING


def test_own_nest_and_others():
    world = two_colonies()
    nest = world.nests[0, 1]
    place(world, (0, 3.0), (4.0, 0))
    world.heading[:] = np.pi / 2
    sight = look(world)
    assert sight.own_nest[0, 0, 0] == pytest.approx(nest - CFG.colonies.nest_radius - 3.0)
    assert sight.other_nest[0, 0, 0] == RANGE and sight.kind[0, 0, 0] == NOTHING
    # facing the other way, from a little below the middle
    place(world, (0, -2.0), (4.0, 0))
    world.heading[:] = -np.pi / 2
    sight = look(world)
    assert sight.other_nest[0, 0, 0] == pytest.approx(nest - CFG.colonies.nest_radius - 2.0)
    assert sight.own_nest[0, 0, 0] == RANGE


def test_a_creature_hides_the_nest_behind_it():
    world = two_colonies()
    place(world, (0, 3.0), (0, 5.5))
    world.heading[:] = np.pi / 2
    sight = look(world)
    assert sight.kind[0, 0, 0] == CREATURE and not sight.nestmate[0, 0, 0]
    assert sight.own_nest[0, 0, 0] == RANGE


def test_standing_on_the_nest_sees_it_straight_away():
    world = two_colonies()
    place(world, tuple(world.nests[0]), (4.0, 0))
    world.heading[:] = -np.pi / 2
    assert look(world).own_nest[0, 0, 0] == pytest.approx(R + GAP)


def test_fan_spreads_across_fov():
    d = directions(np.zeros((1, 1)), CFG.vision.rays, CFG.vision.fov)
    angles = np.arctan2(d[0, 0, :, 1], d[0, 0, :, 0])
    assert angles[0] == pytest.approx(-CFG.vision.fov / 2) and angles[-1] == pytest.approx(CFG.vision.fov / 2)
    assert np.diff(angles) == pytest.approx(np.full(CFG.vision.rays - 1, CFG.vision.fov / (CFG.vision.rays - 1)))


def test_agrees_with_pymunk():
    """With the food gone, everything a ray can hit is a pymunk shape, so pymunk's own queries are the answer."""
    world = World(CFG, 4, seed=7)
    act = RandomActions(4, len(world.colony), 7)
    for _ in range(200):
        world.step(act())
    world.food_regrow[:] = 1
    dist, kind = seen(world)
    dirs = directions(world.heading, CFG.vision.rays, CFG.vision.fov)
    start = R + GAP
    for a, space in enumerate(world.physics.spaces):
        for i, (x, y) in enumerate(world.pos[a]):
            for r, (dx, dy) in enumerate(dirs[a, i]):
                hit = space.segment_query_first((x + dx * start, y + dy * start), (x + dx * RANGE, y + dy * RANGE),
                                                0, pymunk.ShapeFilter())
                want = RANGE if hit is None else start + hit.alpha * (RANGE - start)
                assert dist[a, i, r] == pytest.approx(want, abs=1e-6)
                assert (kind[a, i, r] == NOTHING) == (hit is None)
