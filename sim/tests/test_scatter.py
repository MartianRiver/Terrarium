from dataclasses import replace

import numpy as np
import pytest

from terrarium import World, load
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
