from dataclasses import replace

import numpy as np
import pytest

from terrarium import load
from terrarium.config import DEFAULT, load_train
from terrarium.forage import Forage

CFG = load(DEFAULT)


def meal(energy: float) -> float:
    """The reward for one tick standing on a berry at this energy, paid by needs alone."""
    train = load_train()
    paid = replace(train, reward=replace(train.reward, food=0.0, home=0.0, colony=0.0, needs=1.0))
    env = Forage(CFG, paid, 1, 0)
    w = env.world
    w.energy[:] = energy
    w.food_present[0, 0] = True
    w.food_pos[0, 0] = w.pos[0, 0]
    _, reward, *_ = env.step(np.zeros((env.samples, 5)))
    return float(reward[0])


def test_a_meal_pays_more_the_hungrier_it_finds_you():
    food = CFG.energy.food
    # hunger 0.7 → 0.3, minus a tick's drain
    assert meal(0.3) == pytest.approx(0.7**2 - (0.7 - food)**2, rel=0.01)
    assert meal(0.3) > meal(1 - food) > 0


def test_a_full_one_gets_nothing():
    assert meal(1.0) == 0
