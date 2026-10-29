from types import SimpleNamespace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.tag import Tag

TAG = load(DEFAULT.parent / 'nursery-tag.toml')


def game(spots):
    """A tag game in one arena with Terrikins standing at spots, the first one it and ready to tag."""
    world = SimpleNamespace(cfg=TAG, alive=np.ones((1, len(spots)), bool), pos=np.array([spots], float),
                            rng=np.random.default_rng(0))
    tag = Tag(world)
    tag.it[0], tag.wait[0] = 0, 0
    return world, tag


def wait_out(tag):
    for _ in range(round(TAG.tag.cooldown * TAG.tick_hz) + 1):
        tag.step()


def test_a_touch_passes_it_on_and_it_cant_be_passed_straight_back():
    world, tag = game([(0, 0), (0.9, 0), (5, 5)])
    tag.step()
    assert tag.it[0] == 1 and tag.tags[0, 0] == 1
    wait_out(tag)
    assert tag.it[0] == 1


def test_someone_else_can_be_tagged_and_then_the_first_is_fair_game():
    world, tag = game([(0, 0), (0.9, 0), (1.8, 0)])
    tag.step()
    assert tag.it[0] == 1
    world.pos[0, 0] = (-5, -5)
    wait_out(tag)
    assert tag.it[0] == 2
    world.pos[0, 0] = (2.7, 0)
    world.pos[0, 1] = (5, 5)
    wait_out(tag)
    assert tag.it[0] == 0
