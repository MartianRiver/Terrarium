from dataclasses import replace

import numpy as np
import pytest

from terrarium.config import DEFAULT, load
from terrarium.forage import observe
from terrarium.schema import SELF
from terrarium.smell import Field
from terrarium.world import World

VAULT = load(DEFAULT.parent / 'vault.toml')
OPEN = replace(VAULT.smell, leak=0.1)


def spread(field, food, ticks, blocks=None):
    pos = np.array([[food]], float)
    present = np.ones((1, 1), bool)
    k = len(field.blocks)
    for _ in range(ticks):
        field.step(pos, present, np.zeros((1, k, 2)) if blocks is None else blocks, np.zeros((1, k)))


def test_smell_rises_toward_food():
    field = Field(OPEN, 1, 20.0, (), [])
    spread(field, (0.0, 0.0), 300)
    # three metres east of the food, facing north: it gets stronger to the west, a quarter turn to the left
    strength, sin, cos = field.sense(np.array([[[3.0, 0.0]]])[0], np.array([[np.pi / 2]]))
    assert 0 < strength[0, 0] < 1
    assert sin[0, 0] == pytest.approx(1, abs=0.05) and cos[0, 0] == pytest.approx(0, abs=0.05)
    near, _, _ = field.sense(np.array([[1.0, 0.0]]), np.zeros((1, 1)))
    assert near[0, 0] > strength[0, 0]


def test_none_sensed_before_it_spreads_or_after_a_reset():
    field = Field(OPEN, 1, 20.0, (), [])
    strength, sin, cos = field.sense(np.array([[[3.0, 0.0]]])[0], np.zeros((1, 1)))
    assert strength[0, 0] == 0 and sin[0, 0] == 0 and cos[0, 0] == 0
    spread(field, (0.0, 0.0), 100)
    field.reset(np.array([0]))
    assert not field.smell.any()


def vault_field(leak):
    world = World(VAULT)
    field = Field(replace(VAULT.smell, leak=leak), 1, VAULT.arena.size, VAULT.block, world.doors)
    spread(field, (0.0, 0.0), 600, world.block_pos[:1])
    return field


def at(field, x, y):
    return field.sense(np.array([[x, y]]), np.zeros((1, 1)))[0][0, 0]


def test_walls_hold_it_in_and_doors_let_some_out():
    shut = vault_field(0.0)
    assert at(shut, 0.0, 1.0) > 0.5
    assert at(shut, 4.0, 0.0) == 0 and at(shut, 0.0, 4.5) == 0
    leaky = vault_field(0.1)
    # outside the east door it smells; outside the north wall, as far from the room, less
    assert at(leaky, 4.0, 0.0) > at(leaky, 0.0, 4.5)


def test_off_by_default_and_sensed_as_zeros():
    world = World(load(DEFAULT))
    assert world.smell is None
    me = observe(world, np.zeros((1, world.pos.shape[1], 2))).me
    for name in ('smell', 'smell_sin', 'smell_cos'):
        assert not me[..., SELF.index(name)].any()


def test_the_vault_smells_once_its_food_has_grown():
    world = World(VAULT, seed=3)
    for _ in range(200):
        world.step(np.zeros((1, world.pos.shape[1], 6)))
    me = observe(world, np.zeros((1, world.pos.shape[1], 2))).me
    assert me[..., SELF.index('smell')].max() > 0
