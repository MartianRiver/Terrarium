from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.config import DEFAULT
from terrarium.evals import POLICIES, main, run

SOLO = load(DEFAULT.parent / 'solo.toml')
SHORT = replace(SOLO, episode=replace(SOLO.episode, seconds=20.0))


def test_same_policy_same_numbers():
    assert run(SHORT, POLICIES['random'], 4) == run(SHORT, POLICIES['random'], 4)


def test_time_alive_stops_at_the_episode():
    r = run(SHORT, POLICIES['greedy'], 4)
    assert r['seconds_alive']['max'] <= 20.0


def test_counting_stops_when_an_arena_ends():
    # with no energy to spare everyone dies on the first tick, eats nothing, and the run still finishes
    starving = replace(SHORT, energy=replace(SHORT.energy, start=0.0001))
    r = run(starving, POLICIES['random'], 4)
    assert r['seconds_alive']['max'] == 1 / SOLO.tick_hz and r['food']['max'] == 0


def test_greedy_beats_random():
    """The whole chain at once: rays see food, steering reaches it, eating counts."""
    random, greedy = run(SHORT, POLICIES['random'], 8), run(SHORT, POLICIES['greedy'], 8)
    assert greedy['food_per_minute']['mean'] > 5 * max(random['food_per_minute']['mean'], 0.5)
    assert np.isfinite(greedy['food_per_minute']['stderr'])


def test_runs_without_a_brain(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['evals', '--config', str(DEFAULT.parent / 'solo.toml'), '--policy', 'random', '--episodes', '2'])
    main()
    assert 'random' in capsys.readouterr().out
