from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.vision import FOOD, angles, look
from terrarium.world import World

PEEK = load(DEFAULT.parent / 'nursery-peek.toml')
STILL = np.zeros((1, 1, 7))


def ticks(world, seconds):
    for _ in range(round(seconds * world.cfg.tick_hz)):
        world.step(STILL)


def test_the_berry_turns_up_in_sight_then_hides_where_it_was():
    world = World(PEEK)
    world.step(STILL)
    spot = world.food_pos[0, 0].copy()
    assert (look(world).kind == FOOD).any()
    ticks(world, PEEK.peek.show)
    assert world.peek.hidden[0] and world.food_present[0, 0]
    assert not (look(world).kind == FOOD).any()
    assert np.allclose(world.food_pos[0, 0], spot)


def test_finding_it_pays_and_the_next_turns_up_after_the_gap():
    world = World(PEEK)
    world.step(STILL)
    ticks(world, PEEK.peek.show + 0.5)
    world.food_pos[0, 0] = world.pos[0, 0]
    world.step(STILL)
    assert world.peek.found[0] == 1 and not world.food_present[0, 0]
    assert world.peek.points(world.alive)[0, 0] == PEEK.peek.points
    ticks(world, PEEK.peek.gap + 0.1)
    assert world.food_present[0, 0] and not world.peek.hidden[0]


def test_one_nobody_finds_moves_and_counts_as_missed():
    world = World(PEEK)
    world.step(STILL)
    first = world.food_id[0, 0]
    ticks(world, PEEK.peek.show + PEEK.peek.timeout + 0.1)
    assert world.peek.missed[0] == 1 and world.food_id[0, 0] != first


def test_spin_turns_everyone_round_as_it_hides():
    cfg = replace(PEEK, peek=replace(PEEK.peek, spin=True))
    turns = []
    for spin in (False, True):
        world = World(replace(cfg, peek=replace(cfg.peek, spin=spin)))
        world.step(STILL)
        before = world.heading.copy()
        ticks(world, cfg.peek.show)
        turns.append(not np.allclose(world.heading, before))
    assert turns == [False, True]


def test_facing_a_wall_up_close_doesnt_bring_the_berry_to_you():
    world = World(PEEK, 16)
    world.reset(np.ones(16, bool))
    edge = PEEK.arena.size / 2 - PEEK.creature.radius - 0.05
    world.physics.place(range(16), np.full((16, 1, 2), (edge, 0.0)))
    world.heading[:] = 0.0
    for a in range(16):
        world.peek._place(a)
    gap = np.hypot(*(world.food_pos[:, 0] - world.pos[:, 0]).T)
    assert (gap > PEEK.peek.near / 2).all()


def test_drifting_on_doesnt_find_it_after_the_spin():
    # with no memory, turn to face the way the body still drifts and walk on: before the drift turned with the
    # spin, that found 43% of berries
    cfg = replace(PEEK, peek=replace(PEEK.peek, spin=True))
    world = World(cfg, 16, 7)
    fov = angles(cfg.vision)
    act = np.zeros((16, 1, 7))
    for t in range(round(30 * cfg.tick_hz)):
        if t % 2 == 0:
            sight = look(world)
            food = np.where(sight.kind == FOOD, sight.dist, np.inf)
            sees = np.isfinite(food.min(-1))
            h = world.heading
            fwd = world.vel[..., 0] * np.cos(h) + world.vel[..., 1] * np.sin(h)
            side = world.vel[..., 1] * np.cos(h) - world.vel[..., 0] * np.sin(h)
            drift = np.arctan2(side, fwd)
            moving = np.hypot(fwd, side) > 1e-6
            act = np.zeros((16, 1, 7))
            act[..., 2:] = -1
            act[..., 0] = np.where(sees | ~moving | (np.abs(drift) < 0.25), 1.0, 0.0)
            act[..., 1] = np.where(sees, np.clip(fov[food.argmin(-1)] * 3, -1, 1), np.where(moving, np.clip(drift * 3, -1, 1), 0))
        world.step(act)
    found, missed = world.peek.found.sum(), world.peek.missed.sum()
    assert found / (found + missed) < 0.2


def test_again_it_peeks_out_at_the_same_spot_then_hides_with_a_spin():
    cfg = replace(PEEK, peek=replace(PEEK.peek, spin=True, again=3.0, flash=0.5, timeout=20.0))
    world = World(cfg)
    world.step(STILL)
    spot = world.food_pos[0, 0].copy()
    ticks(world, cfg.peek.show)
    assert world.peek.hidden[0]
    ticks(world, cfg.peek.again - 0.1)
    assert world.peek.hidden[0]
    ticks(world, 0.1)
    assert not world.peek.hidden[0] and np.allclose(world.food_pos[0, 0], spot)
    before = world.heading.copy()
    ticks(world, cfg.peek.flash)
    assert world.peek.hidden[0] and not np.allclose(world.heading, before)
    ticks(world, cfg.peek.again - cfg.peek.flash)
    assert not world.peek.hidden[0]
