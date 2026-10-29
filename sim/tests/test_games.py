from types import SimpleNamespace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.flags import Flags
from terrarium.world import World

FLAG = load(DEFAULT.parent / 'nursery-flag.toml')
SEEK = load(DEFAULT.parent / 'nursery-seek.toml')
NESTS = np.array([[0.0, -6.0], [0.0, 6.0]])


def flag_game(spots):
    """Capture the flag in one arena: colonies 0, 0, 1, 1 standing at spots, nests at either end."""
    world = SimpleNamespace(cfg=FLAG, alive=np.ones((1, 4), bool), pos=np.array([spots], float),
                            colony=np.array([0, 0, 1, 1]), nests=NESTS)
    return world, Flags(world)


def test_walking_into_their_base_takes_their_flag_and_home_captures_it():
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)])
    flags.step()
    assert flags.carrier[0, 1] == 0 and flags.pickups[0, 0] == 1
    world.pos[0, 0] = (0, -6)
    flags.step()
    assert flags.carrier[0, 1] == -1 and flags.captures[0, 0] == 1
    # zero-sum: what colony 0 won, colony 1 lost
    gain = flags.points(world.alive)[0]
    assert gain[0] == gain[1] > 0 and gain[2] == gain[3] == -gain[0]


def test_a_touch_on_the_carrier_sends_their_flag_home():
    world, flags = flag_game([(0, 6), (3, 0), (-5, -1), (5, 1)])
    flags.step()
    world.pos[0, 0] = (0, 2)
    world.pos[0, 2] = (0.5, 2)
    flags.step()
    assert flags.carrier[0, 1] == -1 and flags.saves[0, 1] == 1 and flags.captures.sum() == 0


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
