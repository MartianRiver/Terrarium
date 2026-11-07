from dataclasses import replace

import numpy as np
import pytest
from pymunk import ShapeFilter

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.schema import ACTIONS
from terrarium.world import World

CONFIGS = DEFAULT.parent
SOLO = load(CONFIGS / 'solo.toml')
TREE = load(CONFIGS / 'nursery-tree.toml')
# a tree that walks to a new spot every second, apples growing round it wherever it is
MOVING_TREE = replace(TREE, arena=replace(TREE.arena, scatter=3.0), tree=replace(TREE.tree, move=1.0))
SEED = 2_000_000
# not every array tells a game apart: labels from counters the arenas share, and the buffer forces are written to
LABELS = {'next_id', 'food_id', 'flower_id', 'egg_id', 'id', 'force', 'peek.last'}


def actions(world: World, tick: int, arenas=None, idle=()) -> np.ndarray:
    """Each arena's actions depend on its own number and the tick only, so the same game gets the same ones in any job."""
    n = world.arenas if arenas is None else arenas
    a = np.arange(n)[:, None, None]
    c = np.arange(world.alive.shape[1])[None, :, None]
    k = np.arange(len(ACTIONS))[None, None, :]
    out = np.sin(tick * 0.05 * (a + 1.0) + c + 2.0 * k)
    out[..., 0] = np.abs(out[..., 0]) + 0.3
    out[list(idle)] = -1
    return out


def arrays(world: World, arena: int, drawn=True) -> dict[str, np.ndarray]:
    """Every per-arena array the world and its parts hold, for one arena. Smell's walls are drawn on a first step, so
    right after a reset they're left out. Where a food slot is empty its position is left over from before and unused."""
    out = {}
    owners = {'world': world, 'physics': world.physics}
    for name in ('smell', 'tag', 'seek', 'flags', 'peek', 'dung', 'tree'):
        if getattr(world, name):
            owners[name] = getattr(world, name)
    for owner, obj in owners.items():
        for key, v in vars(obj).items():
            if key in LABELS or f'{owner}.{key}' in LABELS or not isinstance(v, np.ndarray) or v.ndim == 0 or v.shape[0] != world.arenas:
                continue
            out[f'{owner}.{key}'] = v[arena]
    out['world.food_pos'] = np.where(world.food_present[arena][:, None], world.food_pos[arena], 0)
    if not drawn and world.smell:
        out['smell.passes'] = np.zeros(1)
    for key in ('pos', 'vel', 'block_pos', 'block_angle'):
        out[f'physics.{key}'] = getattr(world.physics, key)[arena]
    out['maze_open'] = np.array(sorted(map(sorted, world.maze_open[arena])), dtype=object)
    return out


def same(a: dict, b: dict, what: str):
    # a constant that happens to be as long as one world's arena count is in only that world's list
    assert {'world.food_pos', 'world.food_regrow', 'world.heading', 'world.energy', 'physics.data'} <= a.keys() & b.keys()
    for key in a.keys() & b.keys():
        if a[key].dtype == object:
            assert a[key].tolist() == b[key].tolist(), f'{what}: {key}'
        else:
            assert np.array_equal(a[key], b[key]), f'{what}: {key}'


@pytest.mark.parametrize('cfg', [SOLO, MOVING_TREE], ids=['regrowth', 'moving tree'])
def test_a_game_is_the_same_in_a_job_of_32_64_or_128(cfg):
    worlds = [World(cfg, n, SEED) for n in (32, 64, 128)]
    start = worlds[0].next_id[:32].copy()
    trunk = worlds[0].physics.block_pos[:32, cfg.tree.trunk].copy()
    for t in range(300):
        for w in worlds:
            w.step(actions(w, t))
        if t % 10 == 9:
            for w in worlds[1:]:
                for a in range(32):
                    same(arrays(worlds[0], a), arrays(w, a), f'tick {t}, game {a}, {w.arenas} games')
    # something happened to draw for: food grew back, and the tree moved
    assert (worlds[0].next_id[:32] > start).any()
    if cfg.tree.on:
        assert (worlds[0].physics.block_pos[:32, cfg.tree.trunk] != trunk).any()


@pytest.mark.parametrize('cfg', [SOLO, MOVING_TREE], ids=['regrowth', 'moving tree'])
def test_what_happens_in_one_arena_does_not_change_the_draws_of_another(cfg):
    still, busy = World(cfg, 2, SEED), World(cfg, 2, SEED)
    for t in range(300):
        still.step(actions(still, t, idle=[0]))
        busy.step(actions(busy, t))
        if t % 15 == 0:
            # food eaten in arena 0, as far as the stream goes: a wait to regrow and a new spot
            busy._regrow_wait(np.array([0]))
            busy._grow(0, 0)
        if t % 10 == 9:
            same(arrays(still, 1), arrays(busy, 1), f'tick {t}')
    # arena 0 did differ between them, or this proves nothing
    assert not np.array_equal(still.food_pos[0], busy.food_pos[0])
    assert busy.next_id[0] > still.next_id[0]


def test_the_next_berry_in_one_arena_does_not_depend_on_regrowth_in_another():
    a, b = World(SOLO, 2, SEED), World(SOLO, 2, SEED)
    for _ in range(3):
        b._grow(0, 0)
    b._regrow_wait(np.array([0, 0, 0]))
    a._grow(1, 0)
    b._grow(1, 0)
    assert np.array_equal(a.food_pos[1, 0], b.food_pos[1, 0])


CONFIGS_TRIED = {name: load(CONFIGS / f'{name}.toml') for name in (
    'solo', 'colony', 'night', 'nursery-tag', 'nursery-tree-home', 'nursery-maze', 'nursery-tidy', 'nursery-peek',
    'nursery-seek', 'nursery-flag', 'vault', 'spots')}
CONFIGS_TRIED['moving tree'] = MOVING_TREE


@pytest.mark.parametrize('name', CONFIGS_TRIED)
def test_an_arena_after_a_reset_starts_as_a_fresh_world_does(name):
    cfg = CONFIGS_TRIED[name]
    used, fresh = World(cfg, 2, SEED), World(cfg, 1, SEED)
    for t in range(200):
        used.step(actions(used, t + 3))
    # the games before it have used up arena 0's stream: give it the one a new world's arena 0 starts with
    used.rngs[0] = np.random.default_rng(np.random.SeedSequence(SEED, spawn_key=(0,)))
    used.reset(np.array([True, False]))
    same(arrays(used, 0, drawn=False), arrays(fresh, 0, drawn=False), 'after reset')
    # what physics answers before anything moves
    for p in (fresh.nests[0], fresh.pos[0, 0], fresh.pos[0, -1], (0.0, 0.0), (3.0, 3.0)):
        at = (float(p[0]), float(p[1]))
        hits = [w.physics.spaces[0].point_query_nearest(at, 3.0, ShapeFilter()) for w in (used, fresh)]
        assert [h and (h.distance, h.point) for h in hits[:1]] == [h and (h.distance, h.point) for h in hits[1:]]
    # and what comes of the first ticks, where leftovers show
    for t in range(60):
        used.step(actions(used, t, arenas=2))
        fresh.step(actions(fresh, t, arenas=1))
        if t % 5 == 4:
            same(arrays(used, 0), arrays(fresh, 0), f'tick {t} of the new game')


def test_a_brains_action_noise_is_per_game_from_the_games_seed():
    from terrarium.evals import ActionNoise
    small, big = ActionNoise(5, 4), ActionNoise(5, 8)
    # 3 creatures an arena, 2 actions: the first four games draw the same in a job of four or eight
    assert (small.normal((12, 2), np.float32) == big.normal((24, 2), np.float32)[:12]).all()
    assert (small.random((12, 2)) == big.random((24, 2))[:12]).all()
    a = ActionNoise(5, 2).normal((6, 2), np.float32)
    assert not (a[:3] == a[3:]).all()
    assert not (a == ActionNoise(6, 2).normal((6, 2), np.float32)).all()
