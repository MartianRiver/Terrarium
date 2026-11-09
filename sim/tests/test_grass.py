import base64
from dataclasses import replace

import numpy as np
import pytest

from terrarium import load, replay
from terrarium.config import DEFAULT, Config, ConfigError, build, upgrade
from terrarium.forage import observe
from terrarium.record import record
from terrarium.schema import SELF
from terrarium.world import World
from test_streams import SEED, actions, arrays, same

CONFIGS = DEFAULT.parent
GRASS = load(CONFIGS / 'nursery-grass.toml')
TREE = load(CONFIGS / 'nursery-tree.toml')
G = GRASS.grass
DT = GRASS.dt
DRAIN = GRASS.energy.drain


def idle(world, ticks=1):
    for _ in range(ticks):
        world.step(np.zeros((world.arenas, len(world.colony), 2)))


def put(world, at):
    world.physics.bodies[0][0].position = tuple(at)
    world.physics.read()


def meadow(**kw):
    """The nursery's grass with these numbers changed."""
    return replace(GRASS, grass=replace(G, **kw))


def on_grass(cfg=GRASS, energy=0.5):
    """A world (one arena, one nim) with the nim at the middle of the first meadow."""
    w = World(cfg, 1, 0)
    put(w, w.grass.pos[0, 0])
    w.energy[:] = energy
    return w


def test_a_nim_standing_on_full_cover_gains_bite_times_food_a_second_less_its_drain():
    w = on_grass(meadow(regrow=0.0))
    ticks = round(1 / DT)
    idle(w, ticks)
    assert w.energy[0, 0] == pytest.approx(0.5 + G.bite * G.food - DRAIN, abs=1e-6)
    # the cover it ate: bite a second, from its own cell
    assert w.grass.cover[0].sum() == pytest.approx(w.grass.start[0].sum() - G.bite, abs=1e-4)
    # counted as the food it is, and as grazing
    assert w.grazed[0, 0] == pytest.approx(G.bite * G.food, abs=1e-6)
    assert w.fed[0, 0] == pytest.approx(w.grazed[0, 0]) and w.nourished[0, 0] == pytest.approx(w.grazed[0, 0])
    assert w.grazing[0, 0] == pytest.approx(1.0)


def test_with_still_set_grazing_slows_with_speed_to_nothing_at_still():
    cfg = meadow(still=0.8, regrow=0.0)
    w = on_grass(cfg)
    full = w.grass.start[0].sum()
    # grass.step reads the speed the physics gave the nim
    for speed, share in ((0.0, 1.0), (0.4, 0.5), (0.8, 0.0), (1.5, 0.0)):
        w.grass.cover[:] = w.grass.start
        w.energy[:] = 0.5
        w.vel[:] = (speed, 0.0)
        w.grass.step(1.0)
        assert full - w.grass.cover[0].sum() == pytest.approx(G.bite * DT * share, abs=1e-5)
        assert w.energy[0, 0] - 0.5 == pytest.approx(G.bite * DT * G.food * share, abs=1e-5)


def test_a_nim_walking_through_a_meadow_at_speed_grazes_next_to_nothing_but_one_stopped_does():
    cfg = meadow(still=0.5, radius=2.0, distance=1.0)
    walker, stander = on_grass(cfg), on_grass(cfg)
    for _ in range(30):
        walker.step(np.array([[[1.0, 0.0]]]))
        idle(stander)
    assert stander.grazed[0, 0] > 0.05
    assert walker.grazed[0, 0] < 0.1 * stander.grazed[0, 0]


def test_a_grazed_cell_regrows_at_regrow_up_to_what_it_started_with_and_no_further():
    # a nim that's full and loses nothing eats nothing
    cfg = replace(meadow(regrow=0.5, base=0.3), energy=replace(GRASS.energy, drain=0.0, move=0.0))
    w = World(cfg, 1, 0)
    w.energy[:] = 1.0
    start = w.grass.start[0].copy()
    assert set(np.unique(start).astype(float).round(3)) == {0.3, 1.0}
    w.grass.cover[:] = 0
    idle(w, 10)
    assert w.grass.cover[0] == pytest.approx(np.minimum(start, 0.5 * 10 * DT), abs=1e-6)
    idle(w, 100)
    assert np.array_equal(w.grass.cover[0], start)
    assert w.grass.cover.max() <= 1.0


def test_a_full_nim_doesnt_graze_and_one_nearly_full_takes_only_what_fits():
    # with nothing to pay for staying alive, a nim at 1 has nothing to graze for
    free = replace(GRASS, energy=replace(GRASS.energy, drain=0.0, move=0.0))
    w = on_grass(free, energy=1.0)
    idle(w, 5)
    assert w.grazed[0, 0] == 0 and w.grazing[0, 0] == 0 and np.array_equal(w.grass.cover, w.grass.start)
    # with a drain it eats the drain, no more: it stays at 1
    w = on_grass(energy=1.0)
    idle(w, 5)
    assert w.energy[0, 0] == pytest.approx(1.0) and w.grazed[0, 0] == pytest.approx(5 * DRAIN * DT)
    w.energy[:] = 0.995
    idle(w, 5)
    assert w.energy[0, 0] <= 1.0
    # over a second at 0.1 a second would be 0.1 of energy, 0.25 of cover: it took the 0.005-0.05 that fit
    assert w.grass.start[0].sum() - w.grass.cover[0].sum() < 0.05 / G.food + 1e-6


def test_nims_in_one_cell_share_what_is_left_of_it():
    cfg = replace(GRASS, colonies=replace(GRASS.colonies, size=2), grass=replace(G, regrow=0.0))
    w = World(cfg, 1, 0)
    w.energy[:] = 0.2
    here = w.grass.pos[0, 0]
    for k in range(2):
        w.physics.bodies[0][k].position = tuple(here)
    w.physics.read()
    c = w.grass.cell_of(w.pos)
    assert (c[0, 0] == c[0, 1]).all()
    w.grass.cover[:] = 0
    w.grass.cover[0, c[0, 0, 0], c[0, 0, 1]] = 0.01
    # the grazing alone: stepping the world would push two nims on one spot apart
    w.grass.step(1.0)
    assert w.grass.cover.sum() == pytest.approx(0, abs=1e-7)
    assert w.grazed.sum() == pytest.approx(0.01 * G.food, abs=1e-6)
    assert w.grazed[0, 0] == pytest.approx(w.grazed[0, 1])


def test_the_young_eat_the_same_energy_for_their_share_of_the_cover():
    cfg = replace(GRASS, young=replace(GRASS.young, energy=0.25), grass=replace(G, regrow=0.0))
    w = on_grass(cfg)
    w.young[:] = 100
    idle(w, 20)
    assert w.grazed[0, 0] == pytest.approx(G.bite * G.food, abs=1e-6)
    assert w.grass.start[0].sum() - w.grass.cover[0].sum() == pytest.approx(G.bite * 0.25, abs=1e-4)


def test_grass_is_the_only_food_here_and_a_nim_that_stays_out_of_it_starves_within_the_game():
    w = World(GRASS, 1, 0)
    assert w.wild == 0
    put(w, w.grass.pos[0, 0] + (6.0, 0.0))
    idle(w, round(GRASS.episode.seconds / DT) - 1)
    assert not w.alive[0, 0] and w.grazed[0, 0] == 0


def test_a_nim_left_standing_in_a_meadow_keeps_up_with_its_drain_for_the_whole_game():
    w = on_grass(energy=0.7)
    for _ in range(round(GRASS.episode.seconds / DT)):
        idle(w)
        assert w.alive[0, 0]
    assert w.energy[0, 0] > 0.9


def test_a_world_without_grass_steps_and_replays_as_it_did(tmp_path):
    # [grass]'s other numbers mean nothing without meadows or base cover
    ignored = replace(TREE, grass=replace(TREE.grass, bite=1.0, food=1.0, regrow=1.0, radius=2.0, distance=3.0, cell=0.25))
    assert not TREE.grass.on and not ignored.grass.on
    a, b = World(TREE, 4, SEED), World(ignored, 4, SEED)
    assert a.grass is None
    last = np.zeros((4, 1, 2))
    for t in range(200):
        for w in (a, b):
            w.step(actions(w, t))
        if t % 20 == 0:
            oa, ob = observe(a, last), observe(b, last)
            for x, y in zip((oa.me, oa.kinds, oa.rays), (ob.me, ob.kinds, ob.rays)):
                assert np.array_equal(x, y)
            assert (oa.me[:, -3:] == 0).all()
    for key in ('pos', 'vel', 'block_pos'):
        assert np.array_equal(getattr(a.physics, key), getattr(b.physics, key))
    assert np.array_equal(a.energy, b.energy) and (a.grazed == 0).all()
    path = tmp_path / 'd.jsonl.gz'
    record(TREE, path, 45, seed=4)
    head, frames = replay.read(path)
    assert 'grass' not in head['info'] and all('grass' not in f for f in frames)


def test_old_worlds_read_as_having_no_grass_and_the_loader_is_strict():
    recorded = TREE.to_dict()
    del recorded['grass']
    assert build(Config, upgrade(recorded)).grass == TREE.grass
    for bad in ({'base': 1.5}, {'bite': -1.0}, {'meadows': -1}, {'radius': 0.0}, {'cell': 0.0}):
        with pytest.raises(ConfigError):
            build(Config, upgrade({**GRASS.to_dict(), 'grass': {**GRASS.to_dict()['grass'], **bad}}))
    with pytest.raises(ConfigError):
        build(Config, {**GRASS.to_dict(), 'grass': {'meadows': 1}})


def test_the_sense_is_the_cover_under_it_and_which_way_it_rises_off_its_heading():
    cfg = meadow(regrow=0.0, meadows=1, radius=1.0, distance=2.5)
    w = World(cfg, 1, 0)
    m = w.grass.pos[0, 0]
    # on the bare side of the meadow's edge, level with its middle: the grass is straight ahead if it faces it
    put(w, m + (-1.8, 0.0))
    for heading, (sin, cos) in ((0.0, (0.0, 1.0)), (np.pi / 2, (-1.0, 0.0)), (np.pi, (0.0, -1.0))):
        w.heading[:] = heading
        under, s, c = w.grassed()
        assert under[0, 0] == 0
        assert s[0, 0] == pytest.approx(sin, abs=0.15) and c[0, 0] == pytest.approx(cos, abs=0.15)
    # in the meadow, the cover under it
    put(w, m)
    assert w.grassed()[0][0, 0] == 1.0
    # nothing within reach: even all round, so no direction
    put(w, m + (6.0, 6.0) * np.sign(-m))
    assert [float(x[0, 0]) for x in w.grassed()] == [0.0, 0.0, 0.0]
    # it reaches the brain as the last three inputs, grazing included
    put(w, m + (-1.8, 0.0))
    w.heading[:] = 0.0
    obs = observe(w, np.zeros((1, 1, 2))).me[0]
    assert SELF[-3:] == ('grass', 'grass_sin', 'grass_cos')
    assert obs[-3:] == pytest.approx([0.0, 0.0, 1.0], abs=0.15)


def test_a_meadow_is_where_it_should_be():
    cfg = meadow(meadows=2, distance=2.5, radius=1.0)
    w = World(cfg, 64, SEED)
    for _ in range(3):
        for a in range(64):
            spots = w.grass.pos[a]
            assert (np.abs(spots) <= cfg.arena.size / 2 - 1.0 + 1e-9).all()
            for p in spots:
                assert (np.hypot(*(w.nests - p).T) >= cfg.colonies.nest_radius + 1.0).all()
            assert np.hypot(*(spots[0] - spots[1])) >= 2.0
        w.reset(np.ones(64, bool))
    n = w.grass.n
    assert w.grass.cover.shape == (64, n, n) and set(np.unique(w.grass.start)) <= {0.0, 1.0}
    assert w.grass.start[0].sum() > 10


def test_one_meadow_is_the_set_distance_from_the_nest_in_a_different_direction_each_game():
    cfg = meadow(meadows=1)
    w = World(cfg, 64, SEED)
    d = np.hypot(*(w.grass.pos[:, 0] - w.nests[0]).T)
    assert d == pytest.approx(np.full(64, G.distance))
    assert len({round(float(x), 3) for x in w.grass.pos[:, 0, 0]}) > 30


def test_a_game_on_grass_is_the_same_in_a_job_of_32_or_64():
    worlds = [World(GRASS, n, SEED) for n in (32, 64)]
    for w in worlds:
        w.energy[:] = 0.3
    for t in range(300):
        for w in worlds:
            w.step(actions(w, t))
        if t % 10 == 9:
            for a in range(32):
                same(arrays(worlds[0], a), arrays(worlds[1], a), f'tick {t}, game {a}')
    assert 'grass.cover' in arrays(worlds[0], 0)
    assert (worlds[0].grass.cover[:32] < worlds[0].grass.start[:32]).any()


def test_a_replay_carries_the_cover_once_a_second_and_the_grid_in_its_header(tmp_path):
    path = tmp_path / 'g.jsonl.gz'
    world = record(GRASS, path, 65, seed=4)
    head, frames = replay.read(path)
    assert head['info']['grass'] == {'cell': G.cell, 'n': world.grass.n}
    assert head['source']['config']['grass']['meadows'] == G.meadows
    n = world.grass.n
    shown = [f for f in frames if 'grass' in f]
    assert [f['tick'] for f in shown] == [0, 20, 40, 60]
    first = np.frombuffer(base64.b64decode(shown[0]['grass']), np.uint8)
    # the world it was recorded from: the first game of seed 4
    fresh = World(GRASS, 1, 4)
    assert first.shape == (n * n,) and np.array_equal(first, fresh.grass.bytes(0).ravel())
    assert first.max() == 255 and first.min() == 0


def test_the_cover_in_a_replay_thins_where_a_nim_grazes_and_is_a_byte_a_cell():
    w = on_grass()
    idle(w, 20)
    got = np.frombuffer(base64.b64decode(replay.frame(w, 0)['grass']), np.uint8).reshape(w.grass.n, w.grass.n)
    assert np.array_equal(got, w.grass.bytes(0))
    c = w.grass.cell_of(w.pos)[0, 0]
    assert got[c[0], c[1]] == round(w.grass.cover[0, c[0], c[1]] * 255) < 255
    assert (got[w.grass.start[0] == 0] == 0).all()


def test_grass_comes_off_a_world_with_it_by_zeroing_its_meadows():
    # nursery-grass with meadows 0 and no base cover is the same world without grass: nothing to eat, no senses
    off = meadow(meadows=0)
    w = World(off, 1, 0)
    assert w.grass is None and [float(x[0, 0]) for x in w.grassed()] == [0.0, 0.0, 0.0]
