from dataclasses import replace

import numpy as np
import pymunk
import pytest

from terrarium import World, load
from terrarium.random_actions import RandomActions
from terrarium.vision import BLOCK, CREATURE, FOOD, GAP, NOTHING, WALL, angles, directions, look, reach

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
    d = directions(np.zeros((1, 1)), angles(CFG.vision))
    fan = np.arctan2(d[0, 0, :, 1], d[0, 0, :, 0])
    assert fan[0] == pytest.approx(-CFG.vision.fov / 2) and fan[-1] == pytest.approx(CFG.vision.fov / 2)
    assert np.diff(fan) == pytest.approx(np.full(CFG.vision.rays - 1, CFG.vision.fov / (CFG.vision.rays - 1)))


def test_agrees_with_pymunk():
    """With the food gone, everything a ray can hit is a pymunk shape, so pymunk's own queries are the answer."""
    world = World(CFG, 4, seed=7)
    act = RandomActions(4, len(world.colony), 7)
    for _ in range(200):
        world.step(act())
    world.food_regrow[:] = 1
    dist, kind = seen(world)
    dirs = directions(world.heading, angles(CFG.vision))
    start = R + GAP
    for a, space in enumerate(world.physics.spaces):
        for i, (x, y) in enumerate(world.pos[a]):
            for r, (dx, dy) in enumerate(dirs[a, i]):
                hit = space.segment_query_first((x + dx * start, y + dy * start), (x + dx * RANGE, y + dy * RANGE),
                                                0, pymunk.ShapeFilter())
                want = RANGE if hit is None else start + hit.alpha * (RANGE - start)
                assert dist[a, i, r] == pytest.approx(want, abs=1e-6)
                assert (kind[a, i, r] == NOTHING) == (hit is None)


def ahead(cover, distance):
    """Whether 16 rays over the fov see a berry dead ahead at distance (an even count has no centre ray)."""
    world = alone(rays=16)
    world.cfg = replace(world.cfg, vision=replace(world.cfg.vision, cover=cover))
    world.food_regrow[0, 0] = 0
    world.food_pos[0, 0] = (distance, 0.0)
    return (look(world).kind[0, 0] == FOOD).any()


def test_wide_rays_see_a_berry_dead_ahead():
    assert ahead(0.0, 2.0) and not ahead(0.0, 4.0)
    assert ahead(1.0, 4.0) and ahead(1.0, 7.5)


def test_spread_packs_rays_towards_the_middle_and_side_sees_less_far():
    v = replace(CFG.vision, spread=2.0, side=0.5)
    a = angles(v)
    assert a[0] == pytest.approx(-v.fov / 2) and a[-1] == pytest.approx(v.fov / 2)
    assert np.abs(np.diff(a))[v.rays // 2 - 1] < np.abs(np.diff(a))[0]
    r = reach(v)
    assert r[0] == pytest.approx(v.range / 2) and r.max() < v.range and r.min() == pytest.approx(v.range / 2)


def test_a_flag_is_seen_on_its_nest_but_not_once_someone_carries_it():
    from terrarium.config import DEFAULT
    from terrarium.forage import flag_senses
    from terrarium.vision import FLAG, FLAG_RADIUS
    sight = load(DEFAULT.parent / 'nursery-flag-sight.toml')
    cfg = replace(sight, block=(), colonies=replace(sight.colonies, count=2, size=1),
                  vision=replace(sight.vision, rays=1, fov=0.0))
    world = World(cfg)
    nest = world.nests[1]
    spot = nest + np.array([0.0, -3.0]) * np.sign(nest[1] or 1)
    world.physics.bodies[0][0].position = tuple(spot)
    # the other colony's baby stands aside, out of the ray's way
    world.physics.bodies[0][1].position = (nest[0] + 3.0, nest[1])
    world.physics.read()
    to = nest - world.pos[0, 0]
    world.heading[0, 0] = np.arctan2(to[1], to[0])
    dist, kind = seen(world)
    assert kind[0, 0, 0] == FLAG and dist[0, 0, 0] == pytest.approx(np.hypot(*to) - FLAG_RADIUS, abs=1e-6)
    # carried, it's its carrier the rays see
    world.flags.carrier[0, 1] = 1
    assert seen(world)[1][0, 0, 0] != FLAG
    # with the compass off, the flag senses say who carries what, and nothing of where
    world.flags.carrier[0, 1] = -1
    senses = np.array(flag_senses(world, world.alive.shape))
    assert not senses[[1, 2, 3, 6, 7, 8]].any()
    on = replace(cfg, flag=replace(cfg.flag, sense=True))
    world.cfg = on
    assert np.array(flag_senses(world, world.alive.shape))[1].any()


def test_a_dropping_on_the_heap_is_its_own_kind():
    from terrarium.config import DEFAULT
    from terrarium.vision import DUNG, HEAP
    tidy = load(DEFAULT.parent / 'nursery-tidy-wander.toml')
    cfg = replace(tidy, block=(), colonies=replace(tidy.colonies, count=1, size=1),
                  vision=replace(tidy.vision, rays=1, fov=0.0))
    world = World(cfg)
    world.physics.bodies[0][0].position = (0, 0)
    world.physics.read()
    world.heading[:] = 0
    d = world.dung
    d.left[:], d.held[:], d.heaped[:] = 0, False, False
    d.left[0, 0], d.pos[0, 0] = 100, (2.0, 0)
    dist, kind = seen(world)
    assert kind[0, 0, 0] == DUNG and dist[0, 0, 0] == pytest.approx(2.0 - cfg.dung.radius)
    d.heaped[0, 0] = True
    dist, kind = seen(world)
    assert kind[0, 0, 0] == HEAP and dist[0, 0, 0] == pytest.approx(2.0 - cfg.dung.radius)
    # a loose one in front of the heap is the one seen
    d.left[0, 1], d.pos[0, 1] = 100, (1.0, 0)
    assert seen(world)[1][0, 0, 0] == DUNG


def trunk_sweep(cover, rays=17, fov=3.49, trunk_w=0.5, headings=400):
    """A trunk_w-wide block 10 m ahead of a nim at the centre; for each heading across the fan, whether a ray sees it."""
    block = replace(CFG.block[0], x=10.0, y=0.0, angle=0.0, w=trunk_w, h=trunk_w)
    world = alone(rays=rays, blocks=(block,))
    world.cfg = replace(world.cfg, vision=replace(world.cfg.vision, cover=cover, fov=fov, range=12.0, side=1.0, spread=1.0))
    out = []
    # the trunk's bearing from the heading runs across the fan, kept inside its edges
    for off in np.linspace(-fov / 2 + 0.01, fov / 2 - 0.01, headings):
        world.heading[:] = -off
        dist, kind = seen(world)
        out.append((kind == BLOCK).any())
    return np.array(out)


def test_a_small_trunk_far_off_is_seen_at_every_heading_by_rays_that_cover_the_fan():
    assert trunk_sweep(cover=1.0).all()


def test_a_trunk_between_thin_rays_is_missed_and_covered_rays_only_help():
    thin, half = trunk_sweep(cover=0.0), trunk_sweep(cover=0.5)
    assert not thin.all() and thin.mean() < 0.5
    assert half.mean() > thin.mean() + 0.2


def test_a_wide_ray_hits_a_box_from_its_side_not_only_down_the_middle():
    block = replace(CFG.block[0], x=6.0, y=1.0, angle=0.0, w=1.0, h=1.0)
    world = alone(rays=1, blocks=(block,))
    world.cfg = replace(world.cfg, vision=replace(world.cfg.vision, cover=1.0, fov=0.5))
    dist, kind = seen(world)
    assert kind[0, 0, 0] == NOTHING
    world = alone(rays=3, blocks=(block,))
    world.cfg = replace(world.cfg, vision=replace(world.cfg.vision, cover=1.0, fov=0.6))
    dist, kind = seen(world)
    assert (kind == BLOCK).any()
    assert (dist[kind == BLOCK] > 4.5).all() and (dist[kind == BLOCK] < 7).all()
