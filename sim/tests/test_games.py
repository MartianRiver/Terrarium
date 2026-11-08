from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from terrarium import load
from terrarium import games
from terrarium.brain import Brain, save
from terrarium.config import DEFAULT
from terrarium.evals import brain_policy
from terrarium.flags import Flags
from terrarium.forage import observe
from terrarium.schema import ACTIONS, SELF
from terrarium.world import World

FLAG = load(DEFAULT.parent / 'nursery-flag.toml')
SENT_HOME = replace(FLAG, flag=replace(FLAG.flag, steal=False, guard=0.0, lie=0.0))
SEEK = load(DEFAULT.parent / 'nursery-seek.toml')
NESTS = np.array([[0.0, -6.0], [0.0, 6.0]])
NONE = np.zeros((1, 4), bool)


@pytest.fixture
def scoring_brain(tmp_path):
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    with torch.random.fork_rng():
        torch.manual_seed(17)
        brain = Brain(width=16, layers=1, heads=2, memory=4)
    brain.eval()
    path = tmp_path / 'brain.pt'

    def checkpoint(repeat):
        save(brain, path, repeat=repeat)
        return path, brain

    yield checkpoint
    torch.set_num_threads(threads)


@pytest.mark.parametrize('repeat,switch_after', [(1, 0), (4, 0), (4, 3)])
def test_mixed_policy_observes_executed_steering_after_tag_changes(scoring_brain, monkeypatch, repeat, switch_after):
    path, reference = scoring_brain(repeat)
    cfg = load(DEFAULT.parent / 'nursery-tag.toml')
    cfg = replace(cfg, episode=replace(cfg.episode, seconds=9 / cfg.tick_hz))
    previous, notes, choices = None, None, []
    steering = [SELF.index('last_thrust'), SELF.index('last_turn')]

    def watch_brain(obs, proposed, before):
        nonlocal notes
        expected = np.zeros_like(proposed[..., :2]) if previous is None else previous
        np.testing.assert_array_equal(obs.me[:, steering], expected.reshape(-1, 2).astype(np.float32))
        if notes is None:
            notes = reference.blank(len(before))
        torch.testing.assert_close(before, notes, rtol=0, atol=0)
        _, notes = reference.act(observe(world, expected), sample=False, notes=notes)
        choices.append(proposed.copy())

    def make(w):
        nonlocal world
        world = w
        # Keep the role change isolated from collisions and the tag cooldown.
        w.tag.it[:] = 0
        w.tag.wait[:] = w.episode_ticks + 1
        return brain_policy(path, watch=watch_brain)(w)

    def opponent(w):
        still = games.still(w)

        def act(w):
            x = still(w)
            x[..., :2] = (-0.75, 0.5)
            return x
        return act

    def watch(w, tick):
        nonlocal previous
        previous = played[-1][..., :2].copy()
        if tick == switch_after:
            w.tag.it[:] = 1

    played = []
    world = None

    step = World.step

    def record(w, x):
        played.append(x.copy())
        step(w, x)

    monkeypatch.setattr(World, 'step', record)
    games.play(cfg, 1, 23, [(lambda w: w.tag.mask(), make), (games.everyone, opponent)], watch)
    assert len(choices) == (9 + repeat - 1) // repeat
    assert not np.array_equal(played[0][0, 1, :2], choices[0][0, 1, :2])
    # Notes also advanced for the creatures controlled by the opponent.
    assert torch.count_nonzero(notes[1:]) > 0


@pytest.mark.parametrize('repeat', [1, 4])
def test_self_play_matches_policy_owned_history_bit_for_bit(scoring_brain, repeat):
    path, _ = scoring_brain(repeat)
    cfg = load(DEFAULT.parent / 'nursery-tag.toml')
    cfg = replace(cfg, episode=replace(cfg.episode, seconds=12 / cfg.tick_hz))

    def run(feedback):
        choices, trajectory = [], []

        def watch_brain(obs, actions, notes):
            choices.append((obs.me.copy(), obs.kinds.copy(), obs.rays.copy(), actions.copy(), notes.numpy().copy()))

        def make(w):
            act = brain_policy(path, watch=watch_brain)(w)
            # Without the hook, brain_policy keeps its own proposal, as before the fix.
            return act if feedback else lambda w: act(w)

        def watch(w, tick):
            trajectory.append((w.pos.copy(), w.vel.copy(), w.heading.copy(), w.tag.it.copy(), w.tag.tags.copy()))
            # Exercise changing masks even if these short games have no natural tag.
            w.tag.it[:] = tick % len(w.colony)

        world, walked = games.play(cfg, 2, 23, [(lambda w: w.tag.mask(), make), (games.everyone, make)], watch)
        return choices + trajectory + [(walked, world.energy)]

    old, new = run(False), run(True)
    assert len(old) == len(new)
    for a, b in zip(old, new):
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)


def flag_game(spots, cfg=FLAG):
    """Capture the flag in one arena: colonies 0, 0, 1, 1 standing at spots, nests at either end."""
    world = SimpleNamespace(cfg=cfg, alive=np.ones((1, 4), bool), pos=np.array([spots], float),
                            colony=np.array([0, 0, 1, 1]), nests=NESTS)
    return world, Flags(world)


def test_walking_into_their_base_takes_their_flag_and_home_captures_it():
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)])
    flags.step(NONE)
    assert flags.carrier[0, 1] == 0 and flags.pickups[0, 0] == 1
    world.pos[0, 0] = (0, -6)
    flags.step(NONE)
    assert flags.carrier[0, 1] == -1 and flags.captures[0, 0] == 1
    # zero-sum: what colony 0 won, colony 1 lost
    gain = flags.points(world.alive)[0]
    assert gain[0] == gain[1] > 0 and gain[2] == gain[3] == -gain[0]


def test_a_pickup_pays_the_takers_and_costs_the_others_only_its_charge():
    fair = replace(FLAG, flag=replace(FLAG.flag, charge=0.0))
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)], fair)
    flags.step(NONE)
    gain = flags.points(world.alive)[0]
    assert gain[0] == gain[1] == FLAG.flag.points * FLAG.flag.pickup and gain[2] == gain[3] == 0
    # the capture itself is still zero-sum
    world.pos[0, 0] = (0, -6)
    flags.step(NONE)
    gain = flags.points(world.alive)[0]
    assert gain[0] == FLAG.flag.points and gain[2] == -FLAG.flag.points


def test_carrying_their_flag_home_pays_by_the_metre():
    homeward = replace(FLAG, flag=replace(FLAG.flag, charge=0.0, home=0.1))
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)], homeward)
    flags.step(NONE)
    flags.points(world.alive)
    world.pos[0, 0] = (0, 4)
    flags.step(NONE)
    gain = flags.points(world.alive)[0]
    # 2 m nearer its own nest at (0, -6), paid to its side only
    assert np.isclose(gain[0], 0.2) and np.isclose(gain[1], 0.2) and gain[2] == gain[3] == 0
    world.pos[0, 0] = (0, 5)
    flags.step(NONE)
    assert np.isclose(flags.points(world.alive)[0, 0], -0.1)


def test_without_steal_a_touch_on_the_carrier_sends_their_flag_home():
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)], SENT_HOME)
    flags.step(NONE)
    world.pos[0, 0] = (0, 2)
    world.pos[0, 2] = (0.5, 2)
    flags.step(NONE)
    assert flags.carrier[0, 1] == -1 and flags.saves[0, 1] == 1 and flags.captures.sum() == 0


def wait(flags, seconds):
    for _ in range(round(seconds * FLAG.tick_hz)):
        flags.step(NONE)


def test_a_touch_takes_the_flag_and_its_own_side_has_to_carry_it_home():
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)])
    flags.step(NONE)
    world.pos[0, 0] = (0, 2)
    wait(flags, FLAG.flag.guard)
    world.pos[0, 2] = (0.5, 2)
    flags.step(NONE)
    assert flags.carrier[0, 1] == 2 and flags.saves[0, 1] == 1
    # colony 0 can't take it straight back
    flags.step(NONE)
    assert flags.carrier[0, 1] == 2
    world.pos[0, 2] = (0, 6)
    flags.step(NONE)
    assert flags.carrier[0, 1] == -1 and not flags.down[0, 1] and flags.captures.sum() == 0


def test_a_flag_put_down_is_picked_up_by_a_teammate_and_goes_home_if_left():
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)])
    flags.step(NONE)
    world.pos[0, 0] = (0, 0)
    drop = NONE.copy()
    drop[0, 0] = True
    flags.step(drop)
    assert flags.down[0, 1] and flags.carrier[0, 1] == -1
    # the one who put it down can't pick it straight back up; a teammate can
    flags.step(NONE)
    assert flags.carrier[0, 1] == -1
    world.pos[0, 1] = (0.3, 0)
    flags.step(NONE)
    assert flags.carrier[0, 1] == 1 and not flags.down[0, 1]
    world.pos[0, 1] = (0, 0)
    drop[0, 0], drop[0, 1] = False, True
    flags.step(drop)
    world.pos[0, 0] = world.pos[0, 1] = (3, -3)
    wait(flags, FLAG.flag.lie)
    assert not flags.down[0, 1] and flags.carrier[0, 1] == -1
    assert (flags.where()[0, 1] == NESTS[1]).all()


def test_seekers_stand_still_while_the_hiders_get_away():
    world = World(SEEK)
    go = np.ones((1, len(world.colony), 7))
    held = world.seek.hold(go)
    assert (held[0, world.seek.seeker] == 0).all() and (held[0, ~world.seek.seeker] == 1).all()
    world.age[:] = round(SEEK.seek.prep * SEEK.tick_hz)
    assert (world.seek.hold(go) == 1).all()


def test_hide_and_seek_points_sum_to_nothing():
    world = World(SEEK)
    world.age[:] = round(SEEK.seek.prep * SEEK.tick_hz)
    world.seek.step()
    points = world.seek.points(world.alive)
    assert abs(points.sum()) < 1e-12 and (points != 0).all()


HOME = load(DEFAULT.parent / 'nursery-tree-home.toml')


def in_nest(burrow=False):
    cfg = replace(HOME, tree=replace(HOME.tree, burrow=burrow), episode=replace(HOME.episode, seconds=0.5))
    world = World(cfg)
    edge = world.nests[0] + np.array([cfg.colonies.nest_radius * 0.8, 0.0])
    world.physics.place(np.array([0]), edge[None, None])
    world.crop[:] = 1
    return world


def doing(**on):
    out = np.full((1, 1, len(ACTIONS)), -1.0)
    out[..., :2] = 0
    for name in on:
        out[..., ACTIONS.index(name)] = 1.0
    return out


def test_the_unload_wipe_fires_when_an_apple_is_stored_and_not_when_it_is_eaten_in_the_nest():
    eating = in_nest()
    eating.energy[:] = 0.2
    wipe = games.unloads(eating)
    eating.step(doing(eat=True))
    assert eating.crop[0, 0] == 0 and eating.stored[0, 0] == 0
    assert not wipe(eating).any()
    storing = in_nest()
    wipe = games.unloads(storing)
    assert not wipe(storing).any()
    storing.step(doing(unload=True))
    assert storing.stored[0, 0] == 1
    assert wipe(storing).all()
    assert not wipe(storing).any()


def test_the_unload_wipe_belongs_to_the_nestmate_that_stored_it():
    cfg = replace(HOME, colonies=replace(HOME.colonies, size=2))
    world = World(cfg)
    wipe = games.unloads(world)
    # one stores a load, the other is carrying its own and eats it in the nest
    world.physics.place(np.array([0]), np.array([[world.nests[0], world.nests[0] + [0.3, 0.0]]]))
    world.crop[:] = 1
    world.energy[:] = [[1.0, 0.2]]
    act = np.full((1, 2, len(ACTIONS)), -1.0)
    act[..., :2] = 0
    act[0, 0, ACTIONS.index('unload')] = 1.0
    act[0, 1, ACTIONS.index('eat')] = 1.0
    world.step(act)
    assert world.crop.tolist() == [[0, 0]]
    assert wipe(world).tolist() == [[True, False]]


def test_the_burrows_carry_down_into_the_nest_is_not_walking():
    def play(burrow):
        def begin(w):
            w.physics.place(np.array([0]), (w.nests[0] + [0.8, 0.0])[None, None])
            w.crop[:] = 1
        cfg = replace(HOME, tree=replace(HOME.tree, burrow=burrow), episode=replace(HOME.episode, seconds=0.5))
        unload = lambda world: lambda w: doing(unload=True).repeat(w.arenas, 0)
        return games.play(cfg, 2, 1, [(games.everyone, unload)], begin=begin)
    assert np.allclose(play(True)[1], 0) and np.allclose(play(False)[1], 0)


def test_tree_games_with_water_count_drinking_and_what_each_died_of():
    water = load(DEFAULT.parent / 'nursery-water.toml')
    out = games.tree_game(water, games.still, 2, 1)
    # standing at the nest, nowhere near the pond: dry at 1 / drain = 66.7 s, well before hunger
    assert np.allclose(out['seconds_alive'], 1 / water.water.drain, atol=0.1)
    assert out['died_of_thirst'].tolist() == [1, 1] and out['starved'].tolist() == [0, 0]
    assert out['drank'].tolist() == [0, 0] and out['alive_at_end'].tolist() == [0, 0]
    assert 'drank' not in games.tree_game(HOME, games.still, 1, 1)
