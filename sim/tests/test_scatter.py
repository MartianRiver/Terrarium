from dataclasses import replace

import numpy as np
import pytest

from terrarium import World, games, load
from terrarium.config import ConfigError
from terrarium.scatter import GAP, apart, corners

CFG = load('configs/nursery-tag-hide.toml')


def boxes(world, a):
    return [corners(replace(b, x=x, y=y, angle=t)) for b, (x, y), t
            in zip(world.cfg.block, world.physics.block_pos[a], world.physics.block_angle[a])]


def test_blocks_land_somewhere_new_each_game_and_never_on_each_other():
    world = World(CFG, 16, seed=3)
    world.reset(np.ones(16, bool))
    first = world.physics.block_pos.copy()
    home = np.array([(b.x, b.y) for b in CFG.block])
    assert (np.hypot(*(first - home).transpose(2, 0, 1)) <= CFG.arena.scatter + 1e-6).all()
    for a in range(16):
        bs = boxes(world, a)
        assert (np.abs(np.array(bs)) <= CFG.arena.size / 2).all()
        assert all(apart(p, q, GAP * 0.99) for i, p in enumerate(bs) for q in bs[i + 1:])
    # nothing a creature spawns on, and nothing shoved apart once the world runs
    assert (np.hypot(*world.pos.transpose(2, 0, 1)) < 2.5).all()
    for _ in range(20):
        world.step(np.zeros((16, len(world.colony), 7)))
    assert np.abs(world.physics.block_pos - first).max() < 1e-3
    world.reset(np.ones(16, bool))
    assert np.abs(world.physics.block_pos - first).min(axis=(0, 2)).max() > 0


def test_boxes_turned_into_each_other_overlap():
    a = corners(replace(CFG.block[0], x=0.0, y=0.0, angle=0.0, w=2.0, h=0.5))
    b = corners(replace(CFG.block[0], x=1.2, y=0.0, angle=np.pi / 2, w=2.0, h=0.5))
    assert not apart(a, b, 0.0)
    assert apart(a, corners(replace(CFG.block[0], x=1.5, y=0.0, angle=np.pi / 2, w=2.0, h=0.5)), 0.1)


def test_scatter_is_only_for_blocks_that_stay_put():
    with pytest.raises(ConfigError):
        World(replace(CFG, block=(replace(CFG.block[0], carry=True),) + CFG.block[1:]))


def test_a_new_world_is_scattered_too_with_its_apples_round_the_tree_where_it_landed():
    # scoring plays a new world's first episode, which was the one layout with every block where it's set
    base = load('configs/nursery-tree-home.toml')
    cfg = replace(base, arena=replace(base.arena, scatter=3.0))
    world = World(cfg, 16, seed=2000000)
    trunk = world.physics.block_pos[:, cfg.tree.trunk]
    home = np.array([cfg.block[cfg.tree.trunk].x, cfg.block[cfg.tree.trunk].y])
    assert len({tuple(np.round(t, 3)) for t in trunk}) == 16 and np.hypot(*(trunk - home).T).max() <= 3.0 + 1e-6
    apples = world.food_regrow[:, :world.wild] == 0
    gap = np.hypot(*(world.food_pos[:, :world.wild] - trunk[:, None]).transpose(2, 0, 1))
    assert (gap[apples] <= cfg.tree.far + 1e-6).all()
    # a world that doesn't scatter starts exactly as before
    assert (World(base, 4, seed=7).physics.block_pos == np.array([(b.x, b.y) for b in base.block])).all()


def test_the_scripted_searchers_find_the_tree_and_the_wipe_comes_on_unloading():
    tree = load('configs/nursery-tree-home.toml')
    tree = replace(tree, arena=replace(tree.arena, scatter=1.5), episode=replace(tree.episode, seconds=45.0))
    for name in ('searcher', 'tree_seen'):
        wipes = {}

        def watch(w, t):
            if 'now' not in wipes:
                wipes['now'], wipes['n'] = games.unloads(w), np.zeros(w.alive.shape[0], int)
            wipes['n'] += wipes['now'](w).sum(1)

        w, _ = games.play(tree, 8, 5, [(games.everyone, games.BASELINES[name])], watch=watch)
        home = w.stored.reshape(8, -1).sum(1)
        # a crop of one apple: every unloading stores one
        assert home.sum() > 0 and (wipes['n'] == home).all(), name
