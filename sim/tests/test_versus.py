from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.versus import mixed, seat
from terrarium.world import World

NIGHT = load(DEFAULT.parent / 'night.toml')
SHORT = replace(NIGHT, episode=replace(NIGHT.episode, seconds=2.0))


def constant(value: float, k: int):
    return lambda world: lambda w: np.full((w.arenas, len(w.colony), k), value)


def test_each_colony_plays_by_its_own_policy_and_actions_a_policy_lacks_are_no():
    world = World(NIGHT, arenas=2)
    act = mixed([constant(0.5, 6), constant(-0.5, 2), constant(1.0, 4)])(world)
    out = act(world)
    assert out.shape == (2, 18, 6)
    assert (out[:, :6] == 0.5).all()
    assert (out[:, 6:12, :2] == -0.5).all() and (out[:, 6:12, 2:] == -1).all()
    assert (out[:, 12:, :4] == 1).all() and (out[:, 12:, 4:] == -1).all()


def test_a_turn_moves_every_entry_one_seat_on():
    turn = seat(SHORT, ['random', 'greedy', 'nester'], 1, episodes=2, seed=0, mode='drawn', device='cpu', threads=1)
    assert turn['order'] == ['greedy', 'nester', 'random']
    assert len(turn['size_end']) == 3 and sum(turn['to_the_end']) <= 6
