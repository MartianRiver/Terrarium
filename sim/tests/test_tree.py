from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, ConfigError
from terrarium.forage import observe
from terrarium.schema import ACTIONS, SELF
from terrarium.world import World

TREE = load(DEFAULT.parent / 'nursery-tree.toml')
JUMP = ACTIONS.index('jump')


def act(jump=False):
    out = np.full((1, 1, len(ACTIONS)), -1.0)
    out[..., :2] = 0
    out[..., JUMP] = 1.0 if jump else -1.0
    return out


def under_an_apple(world):
    """Stand the baby right under the first apple."""
    world.physics.place(np.array([0]), world.food_pos[:1, :1].copy())


def test_a_jump_rises_its_height_and_comes_back_down():
    world = World(TREE)
    world.step(act(True))
    top = 0.0
    for _ in range(40):
        world.step(act())
        top = max(top, world.z[0, 0])
    assert TREE.jump.height * 0.85 < top <= TREE.jump.height
    assert world.z[0, 0] == 0 and world.jumps[0, 0] == 1


def test_no_jump_from_the_air():
    world = World(TREE)
    world.step(act(True))
    world.step(act(True))
    assert world.jumps[0, 0] == 1


def test_apples_hang_round_the_trunk():
    world = World(TREE, 8, seed=3)
    gap = np.hypot(*world.food_pos[:, :TREE.food.count].transpose(2, 0, 1))
    assert (gap >= TREE.tree.near - 1e-9).all() and (gap <= TREE.tree.far + 1e-9).all()


def test_standing_under_one_isnt_enough():
    world = World(TREE)
    under_an_apple(world)
    for _ in range(20):
        world.step(act())
    assert world.meals[0, 0] == 0


def test_jumping_under_one_takes_it_and_pays_even_when_full():
    world = World(TREE)
    world.energy[:] = 1.0
    under_an_apple(world)
    world.step(act(True))
    for _ in range(20):
        world.step(act())
    assert world.meals[0, 0] >= 1
    assert world.tree.points(world.alive)[0, 0] == world.meals[0, 0] * TREE.tree.points
    assert world.tree.points(world.alive)[0, 0] == 0


def test_the_brain_feels_how_high_it_is():
    world = World(TREE)
    world.step(act(True))
    world.step(act())
    obs = observe(world, np.zeros((1, 1, 2)))
    assert 0 < obs.me[0, SELF.index('height')] <= 1


def test_a_branch_out_of_reach_is_refused():
    with pytest.raises(ConfigError):
        World(replace(TREE, tree=replace(TREE.tree, reach=TREE.jump.height)))


HOME = load(DEFAULT.parent / 'nursery-tree-home.toml')
UNLOAD = ACTIONS.index('unload')


def test_an_apple_going_home_is_carried_and_pays_only_once_unloaded_in_the_nest():
    world = World(HOME)
    world.energy[:] = 0.2
    under_an_apple(world)
    world.step(act(True))
    for _ in range(20):
        world.step(act())
    assert world.meals[0, 0] == 1 and world.crop[0, 0] == 1 and world.energy[0, 0] < 0.2
    assert world.tree.points(world.alive)[0, 0] == pytest.approx(-HOME.tree.hop)
    world.physics.place(np.array([0]), world.nests[None, :1].copy())
    unload = act()
    unload[..., UNLOAD] = 1.0
    world.step(unload)
    assert world.crop[0, 0] == 0 and world.stored[0, 0] == 1
    assert world.tree.points(world.alive)[0, 0] == HOME.tree.points


def test_a_full_crop_takes_no_apple():
    world = World(HOME)
    world.crop[:] = HOME.crop.capacity
    under_an_apple(world)
    world.step(act(True))
    for _ in range(20):
        world.step(act())
    assert world.meals[0, 0] == 0


def test_apples_going_home_need_a_crop():
    with pytest.raises(ConfigError):
        World(replace(HOME, crop=replace(HOME.crop, capacity=0)))


def starting(start, scatter=1.0, size=1):
    return replace(HOME, arena=replace(HOME.arena, scatter=scatter), tree=replace(HOME.tree, start=start),
                   colonies=replace(HOME.colonies, size=size))


def check_ring(world, start):
    trunk = world.cfg.block[world.cfg.tree.trunk]
    edge = max(trunk.w, trunk.h) / 2 + world.cfg.creature.radius
    for a in range(world.arenas):
        middle = world.physics.block_pos[a, world.cfg.tree.trunk]
        for c in np.flatnonzero(world.alive[a]):
            gap = world.pos[a, c] - middle
            assert np.hypot(*gap) - edge == pytest.approx(start, abs=0.05)
            toward = np.arctan2(-gap[1], -gap[0])
            assert abs((world.heading[a, c] - toward + np.pi) % (2 * np.pi) - np.pi) < 0.01
            assert world.vel[a, c] == pytest.approx(0)


def test_start_stands_each_baby_round_the_scattered_trunk_facing_it_at_the_start_and_after_a_reset():
    world = World(starting(1.5), 4, seed=2)
    check_ring(world, 1.5)
    # scatter moved the trunk off its set spot, and the babies went to where it is
    assert (np.hypot(*world.physics.block_pos[:, 0].T) > 0.01).all()
    world.step(np.zeros((4, 1, len(ACTIONS))))
    world.reset(np.array([True, False, True, False]))
    world.physics.read()
    check_ring(world, 1.5)


def test_start_spaces_a_colony_evenly_round_the_trunk():
    world = World(starting(1.5, size=3), 2, seed=5)
    check_ring(world, 1.5)
    middle = world.physics.block_pos[0, 0]
    angles = np.sort(np.arctan2(*(world.pos[0, :3] - middle).T[::-1]))
    assert np.diff(np.append(angles, angles[0] + 2 * np.pi)) == pytest.approx(2 * np.pi / 3, abs=0.01)


def test_start_0_leaves_the_nest_spawn_as_it_was():
    off = World(starting(0.0), 3, seed=4)
    plain = World(replace(HOME, arena=replace(HOME.arena, scatter=1.0)), 3, seed=4)
    assert (off.pos == plain.pos).all() and (off.heading == plain.heading).all()
    off.reset(np.ones(3, bool))
    plain.reset(np.ones(3, bool))
    assert (off.pos == plain.pos).all() and (off.heading == plain.heading).all()


def test_start_keeps_the_nest_spawn_when_the_ring_wont_fit():
    # the walls are closer than the ring on every side
    cfg = starting(1.5, scatter=0.0)
    world = World(replace(cfg, arena=replace(cfg.arena, size=4.0)), seed=1)
    nest = World(replace(HOME, arena=replace(HOME.arena, size=4.0)), seed=1)
    assert (world.pos == nest.pos).all() and (world.heading == nest.heading).all()
    assert world.tree.start_fell_back[0] == 1


def test_start_counts_and_warns_for_each_game_it_fell_back_in(caplog):
    cfg = starting(1.5, scatter=0.0)
    with caplog.at_level('WARNING'):
        world = World(replace(cfg, arena=replace(cfg.arena, size=4.0)), 3, seed=1)
    assert world.tree.start_fell_back.tolist() == [1, 1, 1]
    assert 'fell back to the nest spawn' in caplog.text
    fits = World(starting(1.5), 3, seed=1)
    assert fits.tree.start_fell_back.tolist() == [0, 0, 0]
    world.reset(np.array([True, False, False]))
    assert world.tree.start_fell_back.tolist() == [1, 1, 1]


def test_start_below_zero_or_with_the_tree_off_is_refused():
    with pytest.raises(ConfigError):
        replace(HOME.tree, start=-1.0)
    with pytest.raises(ConfigError):
        replace(HOME.tree, points=0.0, start=1.0)


def test_burrow_brings_whoever_unloads_an_apple_at_home_up_at_the_nest_middle_turned_any_way():
    cfg = replace(HOME, tree=replace(HOME.tree, burrow=True))
    world = World(cfg)
    world.crop[:] = 1
    edge = world.nests[0] + np.array([cfg.colonies.nest_radius * 0.8, 0.0])
    world.physics.place(np.array([0]), edge[None, None])
    world.heading[:] = np.pi
    unload = act()
    unload[..., UNLOAD] = 1.0
    world.step(unload)
    assert world.stored[0, 0] == 1
    assert np.hypot(*(world.pos[0, 0] - world.nests[0])) < 0.05
    assert world.heading[0, 0] != np.pi
    # unloading nothing, or with burrow off, leaves it where it stands
    world.step(unload)
    assert np.hypot(*(world.pos[0, 0] - world.nests[0])) < 0.05
    plain = World(HOME)
    plain.crop[:] = 1
    plain.physics.place(np.array([0]), edge[None, None])
    plain.step(unload)
    assert np.hypot(*(plain.pos[0, 0] - edge)) < 0.1


def test_burrow_needs_apples_carried_home():
    with pytest.raises(ConfigError):
        load_tree = replace(HOME.tree, home=False, burrow=True)
        World(replace(HOME, tree=load_tree, crop=replace(HOME.crop, capacity=1)))


def test_a_tree_move_with_nowhere_to_go_is_counted_and_warned(monkeypatch, caplog):
    from terrarium import scatter
    world = World(replace(HOME, tree=replace(HOME.tree, move=1.0)), 2, seed=1)
    monkeypatch.setattr(scatter, 'move', lambda w, a, k: a == 1)
    with caplog.at_level('WARNING'):
        for _ in range(45):
            world.step(np.zeros((2, 1, len(ACTIONS))))
    assert world.tree.moves_failed.tolist() == [2, 0]
    assert 'nowhere to move' in caplog.text


def far_home(view=8.0, wall=False):
    # the nest is 2.8 m from the trunk
    cfg = replace(HOME, vision=replace(HOME.vision, range=view))
    world = World(cfg, 2, seed=1)
    if wall:
        # a thin wall across the line between the nest and the trunk
        nest = world.nests[0]
        across = replace(HOME.block[0], x=nest[0] / 2, y=nest[1] / 2, w=6.0, h=0.1,
                         angle=float(np.arctan2(nest[1], nest[0]) + np.pi / 2))
        world = World(replace(cfg, block=[HOME.block[0], across]), 2, seed=1)
    return world


def test_the_trunk_is_seen_from_home_when_in_range_and_nothing_stands_between():
    assert far_home().tree.seen_from_home().tolist() == [True, True]
    assert far_home(view=2.0).tree.seen_from_home().tolist() == [False, False]
    assert far_home(wall=True).tree.seen_from_home().tolist() == [False, False]


def test_the_burrows_carry_is_recorded_and_clears_the_next_step():
    cfg = replace(HOME, tree=replace(HOME.tree, burrow=True))
    world = World(cfg)
    world.crop[:] = 1
    edge = world.nests[0] + np.array([cfg.colonies.nest_radius * 0.8, 0.0])
    world.physics.place(np.array([0]), edge[None, None])
    unload = act()
    unload[..., UNLOAD] = 1.0
    world.step(unload)
    assert np.hypot(*world.tree.jumped[0, 0]) > 0.5
    assert world.pos[0, 0] == pytest.approx(world.nests[0])
    world.step(act())
    assert (world.tree.jumped == 0).all()


# the trunk's scent: a world with smell on, nobody smelling any apples (night)
SMELLY = replace(TREE, arena=replace(TREE.arena, size=32.0), smell=replace(TREE.smell, cell=0.5, spread=0.2, fade=0.001, leak=0.1))
SCENTED = replace(SMELLY, tree=replace(SMELLY.tree, scent=1.0))


def smell_for(cfg, ticks, arenas=1):
    world = World(cfg, arenas, seed=2)
    assert world.smell
    nobody = np.zeros_like(world.food_present)
    for _ in range(ticks):
        world.smell.step(world.food_pos, nobody, world.block_pos, world.block_angle, cfg.tree.scent)
    return world


def test_no_scent_leaves_the_smell_as_it_was():
    off = smell_for(SMELLY, 200).smell
    assert off and not off.smell.any() and off.trunk is None
    # with apples out it is the same field whether or not the dial is passed
    a, b = World(SMELLY, 2, seed=2), World(SMELLY, 2, seed=2)
    assert a.smell and b.smell
    for _ in range(100):
        a.smell.step(a.food_pos, a.food_present, a.block_pos, a.block_angle)
        b.smell.step(b.food_pos, b.food_present, b.block_pos, b.block_angle, 0.0)
    assert a.smell.smell.any() and (a.smell.smell == b.smell.smell).all()


def test_scent_pulls_toward_the_trunk_from_ten_metres():
    world = smell_for(SCENTED, 600, arenas=4)
    assert world.smell
    trunk = world.block_pos[:, SCENTED.tree.trunk]
    for t in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        pos = trunk + 10 * np.array([np.cos(t), np.sin(t)])
        keep = (np.abs(pos) < SCENTED.arena.size / 2 - 0.5).all(1)
        _, sin, cos = world.smell.sense(pos[:, None], np.zeros((4, 1)))
        off = np.abs((np.arctan2(sin[:, 0], cos[:, 0]) - (t + np.pi) + np.pi) % (2 * np.pi) - np.pi)
        assert keep.any() and (off[keep] < np.pi / 4).all()


def test_scent_needs_smell_and_the_tree_on():
    with pytest.raises(ConfigError, match='smell'):
        World(replace(TREE, tree=replace(TREE.tree, scent=1.0)))
    with pytest.raises(ConfigError, match='scent'):
        replace(TREE.tree, points=0.0, scent=1.0)
