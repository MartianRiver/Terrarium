from dataclasses import replace

import numpy as np
import pytest

from terrarium import load, replay
from terrarium.config import DEFAULT, Config, ConfigError, build, upgrade
from terrarium.forage import observe
from terrarium.record import record
from terrarium.schema import RAY, SELF
from terrarium.vision import GAP, look
from terrarium.world import World
from test_streams import SEED, actions, arrays, same

CONFIGS = DEFAULT.parent
WATER = load(CONFIGS / 'nursery-water.toml')
TREE = load(CONFIGS / 'nursery-tree.toml')
T = WATER.water
DT = WATER.dt


def still(world, ticks=1):
    for _ in range(ticks):
        world.step(np.zeros((world.arenas, len(world.colony), 2)))


def put(world, pond=None, at=None):
    """The nim at `at`, the pond at `pond` (arena 0, one nim)."""
    if at is not None:
        world.physics.bodies[0][0].position = tuple(at)
        world.physics.read()
    if pond is not None:
        world.ponds.pos[0, 0] = pond


def far_pond(world):
    # a pond nowhere near the nim, wherever it stands
    return world.pos[0, 0] + (6.0, 0.0)


def test_water_is_off_unless_asked_for():
    assert not TREE.water.on and WATER.water.on
    assert World(TREE, 1, 0).ponds is None


def test_water_drains_over_time_and_the_young_pay_their_share():
    w = World(WATER, 1, 0)
    put(w, pond=far_pond(w))
    assert w.water[0, 0] == 1
    still(w, 40)
    assert w.water[0, 0] == pytest.approx(1 - T.drain * 40 * DT)
    w.young[:] = 100
    before = w.water[0, 0]
    still(w, 20)
    assert before - w.water[0, 0] == pytest.approx(T.drain * 20 * DT * WATER.young.energy)


def test_it_fills_inside_a_pond_and_not_outside():
    w = World(WATER, 1, 0)
    w.water[:] = 0.2
    put(w, pond=far_pond(w))
    still(w, 20)
    assert w.water[0, 0] < 0.2
    put(w, pond=w.pos[0, 0])
    assert w.ponds.inside()[0, 0]
    still(w, 20)
    assert w.water[0, 0] > 0.2
    # clipped at full
    still(w, 200)
    assert w.water[0, 0] == 1
    # the edge: centre just outside the radius is outside
    put(w, pond=w.pos[0, 0] + (T.radius + 0.01, 0.0))
    assert not w.ponds.inside()[0, 0]
    put(w, pond=w.pos[0, 0] + (T.radius - 0.01, 0.0))
    assert w.ponds.inside()[0, 0]


def test_it_dies_at_0_water_and_not_before():
    w = World(WATER, 1, 0)
    put(w, pond=far_pond(w))
    w.water[:] = 3.5 * T.drain * DT
    for _ in range(3):
        still(w)
        assert w.alive[0, 0] and w.water[0, 0] > 0
    still(w)
    assert w.water[0, 0] == 0 and not w.alive[0, 0]
    # starved of water, not energy
    assert w.energy[0, 0] > 0.9
    # the dead stay as they were, drink nothing
    put(w, pond=w.pos[0, 0])
    still(w, 10)
    assert w.water[0, 0] == 0 and not w.alive[0, 0]


def test_a_drink_on_the_last_tick_saves_it():
    w = World(WATER, 1, 0)
    put(w, pond=w.pos[0, 0])
    w.water[:] = 0
    still(w)
    assert w.alive[0, 0] and w.water[0, 0] > 0


def test_energy_still_kills_with_water_full():
    w = World(WATER, 1, 0)
    put(w, pond=w.pos[0, 0])
    w.energy[:] = 1e-4
    still(w, 5)
    assert not w.alive[0, 0] and w.water[0, 0] > 0.9


def test_a_hatchling_starts_full_and_a_game_starts_over_with_start():
    cfg = replace(WATER, water=replace(T, start=0.6))
    w = World(cfg, 2, 0)
    assert (w.water == 0.6).all()
    w.water[:] = 0.1
    w.reset(np.array([True, False]))
    assert (w.water[0] == 0.6).all() and (w.water[1] == 0.1).all()


def test_with_no_ponds_nothing_changes_and_the_new_senses_read_full_and_nothing():
    # [water]'s other numbers mean nothing without ponds
    ignored = replace(TREE, water=replace(TREE.water, drain=0.5, drink=1.0, start=0.3, radius=2.0, distance=3.0))
    a, b = World(TREE, 4, SEED), World(ignored, 4, SEED)
    last = np.zeros((4, 1, 2))
    for t in range(200):
        for w in (a, b):
            w.step(actions(w, t))
        if t % 20 == 0:
            oa, ob = observe(a, last), observe(b, last)
            for x, y in zip((oa.me, oa.kinds, oa.rays), (ob.me, ob.kinds, ob.rays)):
                assert np.array_equal(x, y)
            assert (oa.me[:, SELF.index('water')] == 1).all()
            # no pond: the range, as `own_nest` with no nest in the way
            assert (oa.rays[..., RAY.index('pond')] == 1).all()
    for key in ('pos', 'vel', 'block_pos'):
        assert np.array_equal(getattr(a.physics, key), getattr(b.physics, key))
    assert np.array_equal(a.energy, b.energy) and (a.water == 1).all() and (b.water == 1).all()
    assert np.array_equal(a.food_pos, b.food_pos)


def test_a_pond_is_where_it_should_be():
    cfg = replace(WATER, water=replace(T, ponds=2))
    w = World(cfg, 64, SEED)
    for _ in range(3):
        for a in range(64):
            ponds = w.ponds.pos[a]
            assert (np.abs(ponds) <= cfg.arena.size / 2 - T.radius + 1e-9).all()
            for p in ponds:
                assert (np.hypot(*(w.nests - p).T) >= cfg.colonies.nest_radius + T.radius).all()
                assert not w._on_block(a, p, np.array([(b.w / 2 + T.radius, b.h / 2 + T.radius) for b in cfg.block]))
            assert np.hypot(*(ponds[0] - ponds[1])) >= 2 * T.radius
        w.reset(np.ones(64, bool))
    assert not w.ponds.fell_back.any()


def test_one_pond_is_the_set_distance_from_the_nest_in_a_different_direction_each_game():
    w = World(WATER, 64, SEED)
    d = np.hypot(*(w.ponds.pos[:, 0] - w.nests[0]).T)
    assert d == pytest.approx(np.full(64, T.distance))
    assert len({round(float(x), 3) for x in w.ponds.pos[:, 0, 0]}) > 30
    w.reset(np.ones(64, bool))
    assert not np.array_equal(w.ponds.pos, World(WATER, 64, SEED).ponds.pos)


def test_a_pond_that_cannot_be_that_far_goes_where_it_fits():
    # 6 m from this nest is out of the arena whichever way it's drawn
    cfg = replace(WATER, water=replace(T, distance=6.0))
    w = World(cfg, 8, SEED)
    assert w.ponds.fell_back.all()
    assert (np.abs(w.ponds.pos) <= cfg.arena.size / 2 - T.radius).all()


def test_ponds_are_placed_the_same_in_any_size_of_job():
    worlds = [World(WATER, n, SEED) for n in (8, 32, 128)]
    for w in worlds[1:]:
        assert np.array_equal(w.ponds.pos[:8], worlds[0].ponds.pos)
    # and the same on a reset, as long as the arena's own stream is where it was
    for w in worlds:
        w.reset(np.ones(w.arenas, bool))
    for w in worlds[1:]:
        assert np.array_equal(w.ponds.pos[:8], worlds[0].ponds.pos)


def test_a_game_with_a_pond_is_the_same_in_a_job_of_32_or_64():
    worlds = [World(WATER, n, SEED) for n in (32, 64)]
    for t in range(300):
        for w in worlds:
            w.step(actions(w, t))
        if t % 10 == 9:
            for a in range(32):
                same(arrays(worlds[0], a), arrays(worlds[1], a), f'tick {t}, game {a}')
    assert 'ponds.pos' in arrays(worlds[0], 0)
    assert (worlds[0].water[:32] < 1).any()


def test_food_and_apples_grow_outside_ponds():
    cfg = replace(WATER, water=replace(T, ponds=1), food=replace(WATER.food, regrow_min=0.1, regrow_max=0.2))
    w = World(cfg, 16, SEED)
    for t in range(400):
        # nobody eats, so only ponds and the regrow draw anything
        w.step(actions(w, t) * 0)
        if t % 50 == 0:
            w.food_regrow[:, :w.wild] = 1
    for a in range(16):
        spots = w.food_pos[a, :w.wild]
        assert (np.hypot(*(spots - w.ponds.pos[a, 0]).T) >= T.radius + cfg.food.radius).all()


def test_rays_say_how_far_the_pond_is_as_they_do_a_nest():
    cfg = replace(WATER, vision=replace(WATER.vision, rays=1, fov=0.0), block=(), tree=replace(WATER.tree, points=0.0),
                  colonies=replace(WATER.colonies, count=1, size=1))
    w = World(cfg, 1, 0)
    w.food_regrow[:] = 1
    put(w, at=(0.0, -2.0), pond=(0.0, 1.0))
    w.heading[:] = np.pi / 2
    assert look(w).pond[0, 0, 0] == pytest.approx(3.0 - T.radius)
    # a pond isn't in the way: the wall behind it still shows
    assert look(w).kind[0, 0, 0] != 0
    # something nearer than the pond's edge hides it, as a nest is hidden
    w.food_regrow[:] = 0
    w.food_pos[0, 0] = (0.0, -1.0)
    assert look(w).pond[0, 0, 0] == cfg.vision.range
    w.food_regrow[:] = 1
    # standing in it, it's right here whichever way it faces (as on a nest); facing away from outside, there's none
    put(w, at=(0.0, 1.0))
    w.heading[:] = -np.pi / 2
    assert look(w).pond[0, 0, 0] == pytest.approx(cfg.creature.radius + GAP)
    put(w, at=(0.0, -2.0))
    assert look(w).pond[0, 0, 0] == cfg.vision.range
    # and it reaches the brain, in range shares
    put(w, at=(0.0, -2.0))
    w.heading[:] = np.pi / 2
    obs = observe(w, np.zeros((1, 1, 2)))
    assert obs.rays[0, 0, RAY.index('pond')] == pytest.approx((3.0 - T.radius) / cfg.vision.range)


def test_water_is_a_self_input_and_pond_the_last_ray_input():
    w = World(WATER, 1, 0)
    w.water[:] = 0.37
    assert SELF[-4] == 'water' and RAY[-1] == 'pond'
    assert observe(w, np.zeros((1, 1, 2))).me[0, SELF.index('water')] == pytest.approx(0.37)


def test_old_worlds_read_as_having_no_water_and_the_loader_is_strict():
    recorded = TREE.to_dict()
    del recorded['water']
    assert build(Config, upgrade(recorded)).water == TREE.water
    with pytest.raises(ConfigError):
        build(Config, upgrade({**WATER.to_dict(), 'water': {**WATER.to_dict()['water'], 'start': 1.5}}))
    with pytest.raises(ConfigError):
        build(Config, upgrade({**WATER.to_dict(), 'water': {**WATER.to_dict()['water'], 'radius': 0.0}}))
    with pytest.raises(ConfigError):
        build(Config, {**WATER.to_dict(), 'water': {'ponds': 1}})


def test_a_replay_carries_the_ponds_and_each_nims_water(tmp_path):
    cfg = replace(WATER, water=replace(T, ponds=2))
    path = tmp_path / 'w.jsonl.gz'
    world = record(cfg, path, 60, seed=4)
    head, frames = replay.read(path)
    got = head['info']['ponds']
    assert len(got) == 2 and all(p['radius'] == T.radius for p in got)
    # the world is the same one: it was recorded as the first game of seed 4, and a pond doesn't move
    assert np.abs(np.array([[p['x'], p['y']] for p in got]) - world.ponds.pos[0]).max() <= 0.0005
    assert head['source']['config']['water']['ponds'] == 2
    water = [c['water'] for f in frames for c in f['creatures']]
    assert len(water) == len(frames) * len(world.colony) and max(water) <= 1 and min(water) < 1
    assert frames[-1]['creatures'][0]['water'] == pytest.approx(world.water[0, 0], abs=0.0005)


def test_a_replay_of_a_world_without_water_has_neither(tmp_path):
    path = tmp_path / 'd.jsonl.gz'
    record(TREE, path, 10, seed=4)
    head, frames = replay.read(path)
    assert 'ponds' not in head['info']
    assert all('water' not in c for f in frames for c in f['creatures'])


def test_with_still_set_walking_through_a_pond_drinks_nothing_and_standing_drinks_it_all():
    lap = replace(WATER, water=replace(WATER.water, still=0.5))
    gained = {}
    for thrust in (0.0, 1.0):
        w = World(lap, 1, 0)
        w.water[:] = 0.2
        go = np.zeros((1, len(w.colony), 2))
        go[..., 0] = thrust
        for _ in range(10):
            put(w, pond=w.pos[0, 0])          # the pond follows it, so it's always in one
            before = w.water[0, 0]
            w.step(go)
        speed = float(np.hypot(*w.vel[0, 0]))
        gained[thrust] = w.water[0, 0] - before
    assert gained[0.0] == pytest.approx((T.drink - T.drain) * DT)
    assert speed > 0.5 and gained[1.0] == pytest.approx(-T.drain * DT)


def test_a_sip_smaller_than_the_drain_does_not_keep_it_alive():
    cfg = replace(WATER, water=replace(T, drink=T.drain * 0.8))
    w = World(cfg, 1, 0)
    put(w, pond=w.pos[0, 0])
    w.water[:] = 0
    still(w)
    assert not w.alive[0, 0]
    w = World(cfg, 1, 0)
    put(w, pond=w.pos[0, 0])
    w.water[:] = 0.5
    still(w, 20)
    assert w.alive[0, 0] and w.water[0, 0] < 0.5
