import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, ConfigError
from terrarium.maze import walls
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
