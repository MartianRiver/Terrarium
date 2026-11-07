from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.forage import observe
from terrarium.schema import ACTIONS, SELF
from terrarium.world import World

COLONY = load(DEFAULT.parent / 'colony.toml')
TREE = load(DEFAULT.parent / 'nursery-tree.toml')


def still(world):
    act = np.full((*world.alive.shape, len(ACTIONS)), -1.0)
    act[..., :2] = 0
    world.step(act)


def sense(world, name):
    last = np.zeros((*world.alive.shape, 2))
    return observe(world, last).me[:, SELF.index(name)]


def test_the_compass_reads_the_world_heading_whichever_way_home_is():
    world = World(COLONY)
    world.heading[0, :] = np.pi / 2
    assert np.allclose(sense(world, 'compass_sin'), 1) and np.allclose(sense(world, 'compass_cos'), 0, atol=1e-6)
    world.heading[0, :] = np.pi
    assert np.allclose(sense(world, 'compass_cos'), -1)


def test_with_the_compass_off_it_reads_0_and_nothing_else_changes():
    world = World(COLONY)
    world.heading[0, :] = np.pi / 3
    last = np.zeros((*world.alive.shape, 2))
    on = observe(world, last).me
    world.cfg = replace(COLONY, home=replace(COLONY.home, compass=False))
    off = observe(world, last).me
    dial = [SELF.index('compass_sin'), SELF.index('compass_cos')]
    assert (off[..., dial] == 0).all() and (on[..., dial] != 0).any()
    assert np.array_equal(np.delete(off, dial, -1), np.delete(on, dial, -1))


def test_the_way_home_fades_with_distance_and_says_when_it_is_gone():
    cfg = replace(COLONY, home=replace(COLONY.home, near=1.0, far=3.0))
    world = World(cfg)
    nest = world.nests[world.colony[0]]
    felt = []
    for d in (0.5, 2.0, 4.0):
        world.pos[0, 0] = nest + (d, 0.0)
        felt.append(sense(world, 'home_felt')[0])
        if d == 4.0:
            assert sense(world, 'home_distance')[0] == 0 and sense(world, 'home_cos')[0] == 0
    assert np.allclose(felt, [1.0, 0.5, 0.0])
    # off, it's felt everywhere as before
    assert (sense(World(COLONY), 'home_felt') == 1).all()


def test_a_moving_midden_takes_its_heap_with_it():
    cfg = replace(COLONY, colonies=replace(COLONY.colonies, count=1, size=1, room=0), block=(),
                  dung=replace(COLONY.dung, every=0, start=1, slots=6, radius=0.08, lasts=60.0, midden=3.0,
                               points=1.0, spot=0.5, heap=2, wander=180.0, move=1.0))
    world = World(cfg)
    dung = world.dung
    spots = [dung.midden_at[0].copy()]
    gap = dung.pos[0][dung.heaped[0]] - dung.midden_at[0]
    # it moves on the tick a second in begins
    still(world)
    for _ in range(3):
        for _ in range(cfg.tick_hz):
            still(world)
        spots.append(dung.midden_at[0].copy())
        assert np.allclose(dung.pos[0][dung.heaped[0]] - dung.midden_at[0], gap)
    assert len({tuple(np.round(s, 6)) for s in spots}) == 4


def test_a_moving_tree_takes_its_apples_with_it_and_misses_everyone():
    cfg = replace(TREE, arena=replace(TREE.arena, scatter=3.0), tree=replace(TREE.tree, move=1.0))
    world = World(cfg, 4, seed=1)
    t = cfg.tree
    trunks = [world.physics.block_pos[:, t.trunk].copy()]
    still(world)
    for _ in range(2):
        for _ in range(cfg.tick_hz):
            still(world)
        trunks.append(world.physics.block_pos[:, t.trunk].copy())
        for a in range(4):
            hanging = world.food_pos[a][world.food_present[a]]
            gap = np.hypot(*(hanging - world.physics.block_pos[a, t.trunk]).T)
            assert (gap <= t.far + 1e-6).all()
    assert not np.allclose(trunks[0], trunks[1]) and not np.allclose(trunks[1], trunks[2])


def test_nothing_moves_without_move():
    world = World(TREE, 2, seed=1)
    at = world.physics.block_pos.copy()
    for _ in range(3 * TREE.tick_hz):
        still(world)
    assert np.allclose(world.physics.block_pos, at)
