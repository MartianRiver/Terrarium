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
    old_id, before = world.food_id[0, 0], world.energy[0, 0]
    world.step(np.zeros((1, len(world.colony), 2)))
    assert not world.food_present[0, 0]
    assert world.energy[0, 0] == pytest.approx(min(1, before + CFG.energy.food - CFG.energy.drain * CFG.dt))
    assert world.eaten == 1

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
