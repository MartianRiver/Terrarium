from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, Config, build, load_train, upgrade
from terrarium.forage import Forage, observe
from terrarium.schema import SELF
from terrarium.world import World

VAULT = load(DEFAULT.parent / 'vault.toml')
EAST_DOOR = 6
# just outside the east door, touching its outer face
OUTSIDE = (3.1 + VAULT.creature.radius + 0.05, 0.0)


def at_door(heading, cfg=VAULT):
    cfg = replace(cfg, colonies=replace(cfg.colonies, count=1, size=1))
    world = World(cfg)
    world.physics.place([0], np.array([[OUTSIDE]]))
    world.heading[:] = heading
    world.clock[:] = 30.0
    return world


def walk(world, thrust, grab, seconds):
    for _ in range(round(seconds * world.cfg.tick_hz)):
        world.step(np.array([[[thrust, 0.0, -1, -1, -1, grab]]]))


def test_a_door_pulls_out():
    world = at_door(0.0)
    walk(world, 1.0, 1, 3)
    assert world.holding[0, 0]
    assert world.block_pos[0, EAST_DOOR, 0] > 4.0


def test_walking_away_without_holding_leaves_the_door():
    world = at_door(0.0)
    walk(world, 1.0, -1, 3)
    assert not world.holding[0, 0]
    assert world.block_pos[0, EAST_DOOR, 0] == pytest.approx(2.85, abs=0.01)


def test_a_door_cant_be_pushed_in():
    world = at_door(np.pi)
    walk(world, 1.0, -1, 3)
    assert world.block_pos[0, EAST_DOOR, 0] > 2.7


def test_walls_dont_move():
    world = at_door(0.0)
    world.physics.place([0], np.array([[(3.1 + VAULT.creature.radius + 0.05, 1.7)]]))
    walk(world, 1.0, 1, 3)
    assert world.holding[0, 0]
    assert np.hypot(*(world.block_pos[0, 2] - (2.85, 1.7))) < 0.01


def test_holding_costs_and_letting_go_is_free():
    held, free = at_door(0.0), at_door(0.0)
    walk(held, 0.0, 1, 1)
    walk(free, 0.0, -1, 1)
    assert free.energy[0, 0] - held.energy[0, 0] == pytest.approx(VAULT.grab.energy, rel=0.05)
    # a grip lasts its seconds after the last yes, then lets go
    walk(held, 0.0, -1, VAULT.grab.seconds - 0.05)
    assert held.holding[0, 0]
    walk(held, 0.0, -1, 0.05)
    assert not held.holding[0, 0] and not held.physics.held


def test_the_brain_feels_its_grip_and_the_dead_let_go():
    world = at_door(0.0)
    walk(world, 0.0, 1, 0.05)
    left = 1 - 1 / round(VAULT.grab.seconds * VAULT.tick_hz)
    assert observe(world, np.zeros((1, 1, 2))).me[0, SELF.index('holding')] == pytest.approx(left)
    world.energy[:] = 1e-6
    walk(world, 0.0, 1, 0.05)
    assert not world.alive[0, 0] and not world.holding[0, 0] and not world.physics.held


def test_middle_patches_grow_in_the_vault():
    world = World(VAULT, 8, 0)
    f = world.food_pos[:, :world.wild]
    inside = (np.abs(f) < 2.6).all(-1)
    patches = VAULT.food.patches
    assert inside[:, [i for i in range(world.wild) if i % patches < VAULT.food.middle]].all()


def test_old_run_records_load_without_grab_or_a_middle():
    recorded = load(DEFAULT).to_dict()
    del recorded['grab'], recorded['food']['middle']
    old = build(Config, upgrade(recorded))
    assert not old.grab.on and old.food.middle == 0


def test_ajar_arenas_start_with_the_doors_pulled_out():
    train = load_train()
    env = Forage(VAULT, replace(train, start=replace(train.start, ajar=1.0)), 2, 0)
    doors = env.world.block_pos[:, [EAST_DOOR, EAST_DOOR + 1]]
    assert np.allclose(np.abs(doors[..., 0]), 3.85) and np.allclose(doors[..., 1], 0)
    # walls stay put
    assert np.allclose(env.world.block_pos[:, 0], (0, 2.85))
    shut = Forage(VAULT, train, 2, 0)
    assert np.allclose(np.abs(shut.world.block_pos[:, EAST_DOOR, 0]), 2.85)


SWING = load(DEFAULT.parent / 'vault-swing.toml')


def test_a_hinged_door_swings_out_about_its_hinge():
    world = at_door(0.0, SWING)
    # outside the door's far end, away from the hinge
    world.physics.place([0], np.array([[(OUTSIDE[0], 0.4)]]))
    walk(world, 1.0, 1, 3)
    assert world.holding[0, 0]
    assert abs(world.physics.block_angle[0, EAST_DOOR]) > 0.5
    # the hinge corner stays where it was
    pin = world.physics.bodies[0][world.physics.creatures + EAST_DOOR].local_to_world((0.25, -0.7))
    assert np.hypot(pin.x - 3.1, pin.y + 0.79) < 0.03


def test_a_hinged_door_cant_swing_in():
    world = at_door(np.pi, SWING)
    world.physics.place([0], np.array([[(OUTSIDE[0], 0.4)]]))
    walk(world, 1.0, -1, 3)
    assert abs(world.physics.block_angle[0, EAST_DOOR]) < 0.05


def test_pulling_a_door_out_is_credited_to_whoever_holds_it():
    world = at_door(0.0)
    walk(world, 1.0, 1, 3)
    # paid up to a metre out, however far it went
    assert world.pulled[0, 0] == pytest.approx(1.0, abs=0.02)
    pushed = at_door(0.0)
    walk(pushed, 1.0, -1, 3)
    assert pushed.pulled[0, 0] == 0


def test_ajar_hinged_doors_start_swung_out_by_the_opening():
    train = load_train()
    start = replace(train.start, ajar=1.0, opening=0.5)
    env = Forage(SWING, replace(train, start=start), 2, 0)
    angles = env.world.physics.block_angle[:, [EAST_DOOR, EAST_DOOR + 1]]
    assert np.all(np.abs(angles) > 0.2) and np.all(np.abs(angles) < 0.5)
    # swung out, not in: their middles are further from the arena's centre
    assert np.all(np.abs(env.world.block_pos[:, [EAST_DOOR, EAST_DOOR + 1], 0]) > 2.85)
    # and the start doesn't count as anyone's pull
    assert not env.world.pulled.any() and np.allclose(env.world.door_out, env.world._door_gap())


def test_old_run_records_load_without_hinges():
    recorded = load(DEFAULT).to_dict()
    for b in recorded['block']:
        del b['hinge']
    assert all(not b.hinge for b in build(Config, upgrade(recorded)).block)
