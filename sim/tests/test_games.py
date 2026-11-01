from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.flags import Flags
from terrarium.world import World

FLAG = load(DEFAULT.parent / 'nursery-flag.toml')
SENT_HOME = replace(FLAG, flag=replace(FLAG.flag, steal=False, guard=0.0, lie=0.0))
SEEK = load(DEFAULT.parent / 'nursery-seek.toml')
NESTS = np.array([[0.0, -6.0], [0.0, 6.0]])
NONE = np.zeros((1, 4), bool)


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
