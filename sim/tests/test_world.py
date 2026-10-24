from dataclasses import replace

import numpy as np
import pytest

from terrarium import ConfigError, World, load
from terrarium.random_actions import RandomActions

CFG = load()


def run(world, ticks, seed=0):
    act = RandomActions(world.arenas, len(world.colony), seed)
    for _ in range(ticks):
        world.step(act())


def alone(**changes):
    """One creature, no blocks: for checking movement without anything in the way."""
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=1), block=(), **changes)
    world = World(cfg)
    world.heading[:] = -np.pi / 2  # its nest is above the centre, so this faces open ground
    return world


def place(world, creature, x, y):
    body = world.physics.bodies[0][creature]
    body.position = (x, y)
    body.velocity = (0, 0)
    world.physics.read()


def worst_overlap(world):
    d = world.pos[:, :, None] - world.pos[:, None]
    dist = np.sqrt((d * d).sum(-1)) + np.eye(len(world.colony)) * 1e9
    return np.maximum(2 * CFG.creature.radius - dist, 0).max()


def test_same_seed_same_world():
    a, b, c = World(CFG, 3, seed=4), World(CFG, 3, seed=4), World(CFG, 3, seed=5)
    for w in (a, b, c):
        run(w, 300)
    assert np.array_equal(a.pos, b.pos) and np.array_equal(a.food_id, b.food_id)
    assert np.array_equal(a.block_pos, b.block_pos) and np.array_equal(a.energy, b.energy)
    assert not np.array_equal(a.pos, c.pos)


def test_block_on_a_spawn_ring_is_refused():
    nest = World(CFG).nests[0]
    near = replace(CFG.block[0], x=float(nest[0]), y=float(nest[1]) - 2.0)
    with pytest.raises(ConfigError, match='spawn inside it'):
        World(replace(CFG, block=(near,)))


def test_start_is_clear():
    world = World(CFG, 8, seed=1)
    assert worst_overlap(world) == 0
    half = CFG.arena.size / 2 - CFG.creature.radius
    assert (np.abs(world.pos) <= half).all()
    for b, block in enumerate(CFG.block):
        gap = np.hypot(block.w, block.h) / 2 + CFG.creature.radius
        assert (np.hypot(*(world.pos - world.block_pos[:, b, None]).transpose(2, 0, 1)) > gap).all()


def test_things_stay_inside_and_apart():
    world = World(CFG, 8, seed=2)
    act = RandomActions(8, len(world.colony), 2)
    half = CFG.arena.size / 2
    worst = 0.0
    for _ in range(1200):
        world.step(act())
        worst = max(worst, worst_overlap(world))
        # a pile-up can squeeze creatures a few cm into a wall or each other (docs/physics.md), never through
        assert (np.abs(world.pos) <= half - CFG.creature.radius + 0.1).all()
        for b, block in enumerate(CFG.block):
            assert (np.abs(world.block_pos[:, b]) <= half - min(block.w, block.h) / 2 + 0.1).all()
    assert worst < 0.15


def test_eating_gives_energy_and_food_regrows_elsewhere():
    world = World(CFG, seed=3)
    world.food_pos[0, 0] = world.pos[0, 0]
    world.energy[0, 0] = 0.5
    old_id, before = world.food_id[0, 0], world.energy[0, 0]
    world.step(np.zeros((1, len(world.colony), 2)))
    assert not world.food_present[0, 0]
    assert world.energy[0, 0] == pytest.approx(min(1, before + CFG.energy.food - CFG.energy.drain * CFG.dt))
    assert world.eaten == 1 and world.meals[0].sum() == 1

    hz = CFG.tick_hz
    for _ in range(round(CFG.food.regrow_max * hz) + 1):
        world.step(np.zeros((1, len(world.colony), 2)))
        if world.food_present[0, 0]:
            break
    assert world.food_present[0, 0]
    assert world.tick >= round(CFG.food.regrow_min * hz)
    assert world.food_id[0, 0] > old_id and world.food_id[0, 0] not in world.food_id[0, 1:]
    nest_gap = CFG.colonies.nest_radius + CFG.food.clearance
    assert (np.hypot(*(world.nests - world.food_pos[0, 0]).T) >= nest_gap).all()


STILL = np.zeros((1, 1, 2))


def test_too_full_to_eat_carries_it_slower():
    world = alone()
    world.food_pos[0, 0] = world.pos[0, 0]
    world.step(STILL)
    assert world.crop[0, 0] == 1 and world.meals[0, 0] == 1 and world.energy[0, 0] < CFG.energy.start
    for _ in range(40):
        world.step(np.array([[[1.0, 0.0]]]))
    speed = np.hypot(*world.vel[0, 0])
    assert speed == pytest.approx(CFG.creature.max_speed * (1 - CFG.crop.slow), rel=0.02)


def test_a_full_crop_walks_over_food():
    world = alone()
    world.crop[:] = CFG.crop.capacity
    world.food_pos[0, 0] = world.pos[0, 0]
    world.step(STILL)
    assert world.food_present[0, 0] and world.meals[0, 0] == 0


UNLOAD = np.array([[[0.0, 0.0, 1.0, -1.0]]])
EAT = np.array([[[0.0, 0.0, -1.0, 1.0]]])


def test_unloading_in_the_nest_fills_its_store():
    world = alone()
    place(world, 0, *world.nests[0])
    world.crop[:] = 2
    world.step(STILL)
    assert world.crop[0, 0] == 2, 'nothing is unloaded unless it chooses to'
    world.step(UNLOAD)
    assert world.crop[0, 0] == 0 and world.store[0, 0] == 2 and world.stored[0, 0] == 2


def test_unloading_outside_a_nest_leaves_jelly_anyone_can_eat():
    world = alone()
    world.food_regrow[:, :world.wild] = 10_000
    world.crop[:] = 2
    world.step(UNLOAD)
    dropped = np.flatnonzero(world.food_present[0])
    assert world.crop[0, 0] == 0 and len(dropped) == 2 and (dropped >= world.wild).all()
    assert world.store[0, 0] == 0 and world.stored[0, 0] == 0
    # full, it walks over jelly rather than eating it or taking it back into its crop
    world.food_pos[0, dropped[0]] = world.pos[0, 0]
    world.energy[:] = 0.9
    world.step(STILL)
    assert world.food_present[0, dropped[0]] and world.crop[0, 0] == 0
    world.energy[:] = 0.5
    world.step(STILL)
    assert not world.food_present[0, dropped[0]] and world.food_regrow[0, dropped[0]] == -1
    assert world.energy[0, 0] == pytest.approx(0.5 + CFG.jelly.energy - CFG.energy.drain * CFG.dt)
    assert world.meals[0, 0] == 0, 'jelly is not a meal found'


def test_unloading_in_a_rivals_nest_feeds_theirs():
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=2, size=1), block=())
    world = World(cfg)
    place(world, 0, *world.nests[1])
    world.crop[:] = 1
    world.step(np.array([[[0.0, 0.0, 1.0, -1.0], [0.0, 0.0, -1.0, -1.0]]]))
    assert list(world.store[0]) == [0, 1] and world.stored[0, 0] == 0


def test_eating_from_its_crop():
    world = alone()
    world.crop[:] = 1
    world.energy[:] = 0.5
    world.step(EAT)
    assert world.crop[0, 0] == 0 and world.energy[0, 0] == pytest.approx(0.9 - CFG.energy.drain * CFG.dt)


def test_a_full_one_cant_eat_its_crop():
    world = alone()
    world.crop[:] = 1
    world.energy[:] = 0.9
    world.step(EAT)
    assert world.crop[0, 0] == 1 and world.fed[0, 0] == 0


def test_only_the_hungry_eat_from_the_store_and_only_at_home():
    world = alone()
    world.store[:] = 2
    world.energy[:] = CFG.jelly.hunger - 0.01
    world.step(EAT)
    assert world.store[0, 0] == 2, 'away from the nest'
    place(world, 0, *world.nests[0])
    world.energy[:] = 0.5
    world.step(EAT)
    assert world.store[0, 0] == 2, 'not hungry'
    world.energy[:] = CFG.jelly.hunger - 0.01
    world.step(EAT)
    assert world.store[0, 0] == 1 and world.jelly[0, 0] == 1
    assert world.energy[0, 0] == pytest.approx(CFG.jelly.hunger - 0.01 + CFG.jelly.energy - CFG.energy.drain * CFG.dt)


def test_the_store_runs_out_lowest_index_first():
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=3), block=())
    world = World(cfg)
    for i in range(3):
        place(world, i, *(world.nests[0] + (0.9 * (i - 1), 0)))
    world.store[:] = 2
    world.energy[:] = 0.1
    world.step(np.repeat(EAT, 3, 1))
    assert list(world.jelly[0]) == [1, 1, 0] and world.store[0, 0] == 0


def test_food_grows_in_patches_that_move_each_episode():
    world = World(CFG, 2, seed=4)
    grown = world.food_pos[:, :world.wild]
    near = np.hypot(*(grown[:, :, None] - world.patch_pos[:, None]).transpose(3, 0, 1, 2)).min(-1)
    assert (near <= CFG.food.patch_radius + 1e-9).all()
    before = world.patch_pos.copy()
    world.crop[:] = 1
    world.store[:] = 3
    world.reset(np.array([True, False]))
    assert not np.allclose(world.patch_pos[0], before[0]) and np.allclose(world.patch_pos[1], before[1])
    assert (world.crop[0] == 0).all() and (world.store[0] == 0).all() and (world.store[1] == 3).all()


def test_energy_drains_with_effort():
    world = alone()
    for _ in range(CFG.tick_hz):
        world.step(np.zeros((1, 1, 2)))
    assert world.energy[0, 0] == pytest.approx(CFG.energy.start - CFG.energy.drain)
    for _ in range(CFG.tick_hz):
        world.step(np.array([[[1.0, 0.0]]]))
    e = CFG.energy
    assert world.energy[0, 0] == pytest.approx(e.start - 2 * e.drain - e.move)


def test_top_speed_and_reverse():
    world = alone()
    for _ in range(40):
        world.step(np.array([[[1.0, 0.0]]]))
    assert np.hypot(*world.vel[0, 0]) == pytest.approx(CFG.creature.max_speed, rel=0.01)
    for _ in range(40):
        world.step(np.array([[[-1.0, 0.0]]]))
    forward = np.array([np.cos(world.heading[0, 0]), np.sin(world.heading[0, 0])])
    assert world.vel[0, 0] @ forward == pytest.approx(-CFG.creature.reverse * CFG.creature.max_speed, rel=0.01)


def push(block_index, seconds=3):
    """One creature lined up behind a block, driving straight at its middle. Returns how far the block went."""
    cfg = replace(CFG, colonies=replace(CFG.colonies, count=1, size=1))
    world = World(cfg)
    block = cfg.block[block_index]
    place(world, 0, block.x - block.w / 2 - cfg.creature.radius - 0.3, block.y)
    world.heading[:] = 0
    start = world.block_pos[0, block_index].copy()
    for _ in range(seconds * cfg.tick_hz):
        world.step(np.array([[[1.0, 0.0]]]))
    moved = world.block_pos[0, block_index] - start
    return moved


def test_pushed_blocks_move_and_heavy_ones_less():
    light, heavy = push(0), push(1)
    assert light[0] > 1.0 and abs(light[1]) < 0.2
    assert heavy[0] > 0 and light[0] > 2 * heavy[0]


def test_running_out_of_energy_kills_and_ends_the_arena():
    world = alone()
    world.energy[0, 0] = 0.01
    world.food_regrow[:] = 1
    ticks = 0
    while world.alive[0, 0]:
        world.step(np.array([[[1.0, 0.0]]]))
        ticks += 1
    assert ticks == int(np.ceil(0.01 / ((CFG.energy.drain + CFG.energy.move) * CFG.dt)))
    assert world.ended[0]
    # dead bodies coast to a stop and don't eat
    world.food_regrow[0, 0] = 0
    world.food_pos[0, 0] = world.pos[0, 0]
    for _ in range(40):
        world.step(np.array([[[1.0, 1.0]]]))
    assert np.hypot(*world.vel[0, 0]) < 0.01 and world.food_present[0, 0] and world.energy[0, 0] == 0


def test_eating_on_the_last_tick_saves_it():
    world = alone()
    world.energy[0, 0] = 0.0001
    world.food_pos[0, 0] = world.pos[0, 0]
    world.step(np.zeros((1, 1, 2)))
    assert world.alive[0, 0] and world.energy[0, 0] > 0.3


def test_episode_runs_out():
    cfg = replace(CFG, episode=replace(CFG.episode, seconds=2.0))
    world = World(cfg, 2)
    run(world, 39)
    assert not world.ended.any()
    run(world, 1)
    assert world.ended.all()


def test_reset_starts_only_those_arenas_over():
    world = World(CFG, 3, seed=5)
    run(world, 200)
    world.alive[1, :3] = False
    world.energy[1, :3] = 0
    before = world.pos.copy(), world.food_id.copy(), world.block_pos.copy()
    world.reset(np.array([False, True, False]))

    assert world.age[1] == 0 and world.age[0] == world.age[2] == 200
    assert world.alive[1].all() and (world.energy[1] == CFG.energy.start).all()
    wild = world.wild
    assert world.food_present[1, :wild].all() and not world.food_present[1, wild:].any()
    assert world.food_id[1, :wild].min() > before[1][1].max()
    assert (world.meals[1] == 0).all()
    assert np.array_equal(world.block_pos[1], [(b.x, b.y) for b in CFG.block])
    assert (world.vel[1] == 0).all() and worst_overlap(world) < 0.15
    for a in (0, 2):
        assert np.array_equal(world.pos[a], before[0][a]) and np.array_equal(world.food_id[a], before[1][a])
        assert np.array_equal(world.block_pos[a], before[2][a])
    # and it carries on from there like a fresh start
    run(world, 100)
    assert world.age[1] == 100


def test_reset_is_deterministic():
    worlds = [World(CFG, 2, seed=9) for _ in range(2)]
    for w in worlds:
        run(w, 100)
        w.reset(np.array([True, False]))
        run(w, 100)
    assert np.array_equal(worlds[0].pos, worlds[1].pos) and np.array_equal(worlds[0].food_pos, worlds[1].food_pos)


def test_a_training_world_can_start_with_full_crops():
    cfg = replace(CFG, crop=replace(CFG.crop, start=CFG.crop.capacity))
    world = World(cfg, 2, seed=3)
    assert (world.crop == CFG.crop.capacity).all()
    world.crop[:] = 0
    world.reset(np.array([True, False]))
    assert (world.crop[0] == CFG.crop.capacity).all() and (world.crop[1] == 0).all()
    with pytest.raises(ConfigError, match='more than a crop holds'):
        World(replace(CFG, crop=replace(CFG.crop, start=CFG.crop.capacity + 1)))


def test_a_spawn_ring_past_the_walls_is_refused():
    with pytest.raises(ConfigError, match='past the walls'):
        World(replace(CFG, block=(), colonies=replace(CFG.colonies, spawn_ring=4.0)))
