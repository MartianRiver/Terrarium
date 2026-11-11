# The main world: several colonies sharing meadows, a pond, one tree and the dark.
from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, ConfigError
from terrarium.schema import ACTIONS
from terrarium.water import FAIR
from terrarium.world import World

MAIN = load(DEFAULT.parent / 'main-world.toml')
UNLOAD, JUMP = ACTIONS.index('unload'), ACTIONS.index('jump')
TRUNK = MAIN.tree.trunk


def idle(world, ticks=1, **yes):
    out = np.zeros((world.arenas, len(world.colony), len(ACTIONS)))
    out[..., 2:] = -1
    for name in yes:
        out[..., ACTIONS.index(name)] = 1.0
    for _ in range(ticks):
        world.step(out)


def test_main_world_loads_with_every_nursery_skill_on():
    c = MAIN
    assert c.colonies.count == 2 and c.grass.on and c.water.on and c.tree.on and c.fat.on and c.jump.height > 0
    assert c.vision.range == 12.0 and c.energy.rest < 1 and c.grass.night == 0
    assert 0 < c.tree.apples < c.food.count


def test_meadows_are_dealt_out_to_the_colonies_each_near_its_own_nest():
    w = World(MAIN, 16, seed=4)
    for k in range(MAIN.grass.meadows):
        own = w.nests[k % 2]
        gap = np.hypot(*(w.grass.pos[:, k] - own).T)
        assert gap == pytest.approx(MAIN.grass.distance)
    assert w.grass.fell_back.sum() == 0


def test_one_colony_still_puts_every_meadow_round_its_one_nest():
    cfg = load(DEFAULT.parent / 'nursery-grass.toml')
    w = World(cfg, 8, seed=1)
    gap = np.hypot(*(w.grass.pos - w.nests[0]).transpose(2, 0, 1))
    assert gap == pytest.approx(cfg.grass.distance)


def test_a_pond_goes_where_neither_colony_is_nearer_at_its_distance_from_the_middle():
    w = World(MAIN, 32, seed=5)
    pond = w.ponds.pos[:, 0]
    near = np.hypot(*(pond[:, None] - w.nests[None]).transpose(2, 0, 1))
    assert (np.abs(near[:, 0] - near[:, 1]) <= FAIR + 1e-9).all()
    assert np.hypot(*(pond - w.nests.mean(0)).T) == pytest.approx(MAIN.water.distance)
    assert w.ponds.fell_back.sum() == 0
    # both sides of the tree turn up
    assert (pond[:, 0] < 0).any() and (pond[:, 0] > 0).any()


def test_a_pond_in_a_one_colony_world_is_still_its_distance_from_that_nest():
    cfg = load(DEFAULT.parent / 'nursery-water.toml')
    w = World(cfg, 8, seed=2)
    gap = np.hypot(*(w.ponds.pos[:, 0] - w.nests[0]).T)
    assert gap == pytest.approx(cfg.water.distance)


def at_night(cfg, night):
    world = World(replace(cfg, grass=replace(cfg.grass, night=night)), 1, seed=3)
    return world


def graze_for(world, seconds, dark):
    n = world.cfg.night
    world.clock[:] = n.cycle - n.length / 2 if dark else 0.0
    world.age[:] = 0
    world.energy[:] = 0.5
    world.fat[:] = 0
    world.water[:] = 1
    a = world.grass
    world.physics.revive([0], [0], np.array([a.pos[0, 0]]))
    a.cover[0] = 0.5 * a.start[0]
    before = a.cover[0].sum()
    # one nim, standing; the rest of the colony is somewhere else
    for _ in range(round(seconds * world.cfg.tick_hz)):
        world.energy[0, 0] = min(world.energy[0, 0], 0.5)
        idle(world)
    return a.cover[0].sum() - before


def test_with_night_0_grass_neither_grows_nor_feeds_in_the_dark_and_does_by_day():
    day = graze_for(at_night(MAIN, 0.0), 2, dark=False)
    dark = graze_for(at_night(MAIN, 0.0), 2, dark=True)
    assert dark == pytest.approx(0.0, abs=1e-6)
    assert day != 0.0


def test_night_1_is_grass_as_it_was_by_day_and_dark_alike():
    a = graze_for(at_night(MAIN, 1.0), 2, dark=True)
    b = graze_for(at_night(MAIN, 1.0), 2, dark=False)
    assert a == pytest.approx(b, rel=0.2) and a != 0.0


def test_night_half_halves_what_the_dark_grows_back_and_feeds():
    world = at_night(MAIN, 0.5)
    # nobody grazing: only regrowth moves the cover
    world.clock[:] = world.cfg.night.cycle - world.cfg.night.length / 2
    world.alive[:] = False
    world.grass.cover[0] = 0.0
    idle(world, 20)
    dark = world.grass.cover[0].max()
    full = at_night(MAIN, 1.0)
    full.clock[:] = world.clock
    full.alive[:] = False
    full.grass.cover[0] = 0.0
    idle(full, 20)
    assert dark == pytest.approx(0.5 * full.grass.cover[0].max(), rel=0.05)


def test_night_is_a_share():
    with pytest.raises(ConfigError):
        replace(MAIN.grass, night=1.5)


def jump_for_an_apple(world, a, i):
    """Put nim i of arena a under the first apple and jump until it holds one; the berries are out of the way."""
    world.food_regrow[:, MAIN.tree.apples:world.wild] = 10_000
    spot = world.food_pos[a, 0].copy()
    world.physics.revive([a], [i], np.array([spot]))
    for _ in range(40):
        idle(world, 1, jump=(world.z[a, i] == 0))
        if world.crop[a, i] > 0:
            return
    raise AssertionError('no apple taken')


def test_berries_are_taken_from_the_ground_and_only_apples_need_a_jump():
    w = World(MAIN, 1, seed=6)
    w.energy[:] = 0.5
    berry = w.food_pos[0, MAIN.tree.apples].copy()
    w.physics.revive([0], [0], np.array([berry]))
    idle(w)
    assert w.meals[0, 0] == 1 and w.crop[0, 0] == 0
    assert w.apples_crop[0, 0] == 0
    # under an apple, standing, nothing
    w2 = World(MAIN, 1, seed=6)
    w2.food_regrow[:, MAIN.tree.apples:w2.wild] = 10_000
    w2.physics.revive([0], [0], np.array([w2.food_pos[0, 0]]))
    idle(w2, 3)
    assert w2.meals[0, 0] == 0


def test_an_apple_is_carried_as_one_and_a_berry_is_not_counted_as_an_apple():
    w = World(MAIN, 1, seed=6)
    w.energy[:] = 1.0
    w.fat[:] = MAIN.fat.capacity
    jump_for_an_apple(w, 0, 0)
    assert w.apples_crop[0, 0] == 1 and w.crop[0, 0] == 1
    w.food_regrow[0, MAIN.tree.apples] = 0
    # a full bar and room in the crop: a berry goes in the crop too, but isn't an apple
    berry = w.food_pos[0, MAIN.tree.apples].copy()
    w.physics.revive([0], [0], np.array([berry]))
    idle(w)
    assert w.crop[0, 0] == 2 and w.apples_crop[0, 0] == 1
    # eating from the crop takes a berry before the apple
    w.energy[:] = 0.5
    idle(w, 1, eat=True)
    assert w.crop[0, 0] == 1 and w.apples_crop[0, 0] == 1


def unload_at_home(w, a, i):
    w.physics.revive([a], [i], np.array([w.nests[w.colony[i]]]))
    idle(w, 1, unload=True)


def test_an_apple_pays_the_colony_that_unloaded_it_not_the_other():
    w = World(MAIN, 1, seed=6)
    w.energy[:] = 1.0
    w.fat[:] = MAIN.fat.capacity
    jump_for_an_apple(w, 0, 0)
    assert w.colony[0] == 0
    w.tree.points(w.alive)
    unload_at_home(w, 0, 0)
    assert w.apples_stored[0, 0] == 1
    paid = w.tree.points(w.alive)[0]
    mine = (w.colony == 0) & w.alive[0]
    assert paid[mine] == pytest.approx(MAIN.tree.points)
    assert (paid[w.colony == 1] == 0).all()


def test_a_berry_unloaded_at_home_pays_the_tree_nothing_while_an_apple_does():
    w = World(MAIN, 1, seed=6)
    w.crop[0, 0] = 1
    w.tree.points(w.alive)
    unload_at_home(w, 0, 0)
    assert w.stored[0, 0] == 1 and w.apples_stored[0, 0] == 0
    assert (w.tree.points(w.alive) == 0).all()


def test_burrow_takes_each_unloader_to_its_own_nest():
    cfg = replace(MAIN, tree=replace(MAIN.tree, burrow=True))
    w = World(cfg, 1, seed=6)
    both = [0, int(np.flatnonzero(w.colony == 1)[0])]
    for i in both:
        w.apples_crop[0, i] = w.crop[0, i] = 1
        edge = w.nests[w.colony[i]] + np.array([cfg.colonies.nest_radius * 0.8, 0.0])
        w.physics.revive([0], [i], np.array([edge]))
    idle(w, 1, unload=True)
    for i in both:
        assert np.hypot(*(w.pos[0, i] - w.nests[w.colony[i]])) < 0.05
    # a berry unloaded doesn't burrow
    w.crop[0, 0] = 1
    edge = w.nests[0] + np.array([cfg.colonies.nest_radius * 0.8, 0.0])
    w.physics.revive([0], [0], np.array([edge]))
    idle(w, 1, unload=True)
    assert np.hypot(*(w.pos[0, 0] - edge)) < 0.2


def test_some_food_on_the_ground_needs_the_apples_carried_home():
    with pytest.raises(ConfigError):
        replace(MAIN.tree, home=False)
    with pytest.raises(ConfigError):
        World(replace(MAIN, tree=replace(MAIN.tree, apples=MAIN.food.count + 1)))
