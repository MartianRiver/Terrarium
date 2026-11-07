import json
from types import SimpleNamespace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, ConfigError
from terrarium.maze import Visits, walls
from terrarium.train import train
from terrarium.world import World

MAZE = load(DEFAULT.parent / 'nursery-maze.toml')


def rooms_reached(n, inner):
    """Every room reachable from the first, going through gaps in inner walls (x, y, angle in rooms)."""
    blocked = {(round(x * 2), round(y * 2)) for x, y, _ in inner}
    seen, todo = {(0, 0)}, [(0, 0)]
    while todo:
        r, c = todo.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (r + dr, c + dc)
            # the wall between two rooms sits halfway: x = c + 0.5 + dc / 2, y = r + 0.5 + dr / 2
            mid = (round((c + 0.5 + dc / 2) * 2), round((r + 0.5 + dr / 2) * 2))
            if 0 <= q[0] < n and 0 <= q[1] < n and q not in seen and mid not in blocked:
                seen.add(q)
                todo.append(q)
    return len(seen)


@pytest.mark.parametrize('n', [2, 3, 5, 8])
def test_a_maze_has_its_walls_and_a_way_to_every_room(n):
    rng = np.random.default_rng(n)
    for _ in range(20):
        inner = walls(n, rng)
        assert len(inner) == (n - 1) ** 2
        assert rooms_reached(n, inner) == n * n


def test_every_episode_is_a_new_maze_with_nothing_inside_a_wall():
    world = World(MAZE, 2, 0)
    layouts = []
    for _ in range(3):
        world.reset(np.ones(2, bool))
        layouts.append(world.physics.block_pos.copy())
        half = np.array([[1.35 + 0.25, 0.15 + 0.25]] * len(MAZE.block))
        for a in range(2):
            for f in np.flatnonzero(world.food_present[a]):
                assert not world._on_block(a, world.food_pos[a, f][None], half)
    assert not np.allclose(layouts[0], layouts[1])
    assert not np.allclose(layouts[0][0], layouts[0][1])
    # the baby starts in the middle room, clear of every wall
    assert np.allclose(world.pos[:, 0], 0, atol=0.01)


def test_a_maze_needs_the_right_number_of_walls():
    from dataclasses import replace
    with pytest.raises(ConfigError):
        World(replace(MAZE, block=MAZE.block[:-1]))


def test_been_here_before_is_only_for_rooms_left_and_come_back_to():
    # only where the creature is matters, so a stand-in world it can be put anywhere in
    world = SimpleNamespace(cfg=load(DEFAULT.parent / 'nursery-maze-3.toml'), alive=np.ones((1, 1), bool), pos=None)
    visits = Visits(world)
    # rooms of 3 m from (-4.5, -4.5): (row, col) = the room's centre at x = col * 3 - 3, y = row * 3 - 3
    at = lambda row, col: np.array([[[col * 3.0 - 3.0, row * 3.0 - 3.0]]])
    seen = []
    for row, col in ((1, 1), (1, 1), (1, 2), (1, 2), (1, 1), (0, 1), (1, 1)):
        world.pos = at(row, col)
        seen.append(visits.update()[0])
    assert seen == [0, 0, 0, 0, 1, 0, 1]
    visits.reset(np.array([True]))
    world.pos = at(1, 2)
    assert visits.update()[0] == 0


def test_training_asks_the_notes_whether_they_have_been_here(tmp_path):
    from test_ppo import short
    world, trainer = short(tmp_path)
    world.write_text((DEFAULT.parent / 'nursery-maze-3.toml').read_text().replace('seconds = 90.0', 'seconds = 6.0'))
    trainer.write_text(trainer.read_text().replace('closure = 0.0', 'closure = 1.0'))
    run = train('closure', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu', memory=8, score=False)
    rows = [json.loads(l) for l in (run.dir / 'metrics.jsonl').read_text().splitlines()]
    assert all(r['closure_loss'] > 0 and 0 <= r['closure_right'] <= 1 for r in rows)
    with pytest.raises(ValueError, match='closure'):
        train('no-memory', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu', score=False)
