from dataclasses import replace

import numpy as np

from terrarium import load
from terrarium.brain import SHAPE, Brain, save
from terrarium.config import DEFAULT
from terrarium.evals import POLICIES, brain_policy, main, run, summary
from terrarium.world import World

SOLO = load(DEFAULT.parent / 'solo.toml')
SHORT = replace(SOLO, episode=replace(SOLO.episode, seconds=20.0))
COLONIES = load(DEFAULT)
COLONIES_SHORT = replace(COLONIES, episode=replace(COLONIES.episode, seconds=20.0))


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
    assert r['deaths']['died'] == r['deaths']['creatures'] == 4 and r['deaths']['colonies_lost'] == 4


def test_greedy_beats_random():
    """The whole chain at once: rays see food, steering reaches it, eating counts."""
    random, greedy = run(SHORT, POLICIES['random'], 8), run(SHORT, POLICIES['greedy'], 8)
    assert greedy['food_per_minute']['mean'] > 5 * max(random['food_per_minute']['mean'], 0.5)
    assert np.isfinite(greedy['food_per_minute']['stderr'])


def test_the_error_is_over_arenas():
    # creatures in one arena move together, so six of them are no surer than one
    x = np.repeat(np.array([[1.0], [2.0], [3.0], [4.0]]), 6, 1)
    assert summary(x)['stderr'] == summary(x[:, :1])['stderr'] > 0
    assert summary(x)['p10'] < summary(x)['mean']


def test_carrier_takes_its_actions_where_they_count():
    actions = run(COLONIES_SHORT, POLICIES['carrier'], 4)['actions']
    assert actions['unload_home']['ticks'] > 0 and actions['unload_home']['yes'] == 1.0
    assert actions['unload_away']['yes'] in (0.0, None)


def test_a_brain_steers_by_its_mean_and_draws_its_yes_no_actions(tmp_path):
    save(Brain(**SHAPE), tmp_path / 'b.pt')
    world = World(SHORT, 4, 0)
    drawn, mean, sampled = (brain_policy(tmp_path / 'b.pt', mode)(world)(world) for mode in ('drawn', 'mean', 'sampled'))
    assert np.array_equal(drawn, brain_policy(tmp_path / 'b.pt')(world)(world))
    assert np.array_equal(drawn[..., :2], mean[..., :2]) and not np.allclose(drawn[..., 2:], mean[..., 2:])
    assert not np.allclose(sampled[..., :2], mean[..., :2])


def test_nights_are_counted():
    # a 10 s day and 5 s night: two whole nights in 32 s
    nights = replace(COLONIES, episode=replace(COLONIES.episode, seconds=32.0),
                     night=replace(COLONIES.night, cycle=15.0, length=5.0, dusk=1.0))
    r = run(nights, POLICIES['greedy'], 2)
    assert r['nights']['max'] == 2 and r['through_first_night'] == 2 * COLONIES.colonies.count
    assert run(COLONIES_SHORT, POLICIES['greedy'], 2)['through_first_night'] is None


def test_runs_without_a_brain(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['evals', '--config', str(DEFAULT.parent / 'solo.toml'), '--policy', 'random', '--episodes', '2'])
    main()
    assert 'random' in capsys.readouterr().out


def test_flowers_drunk_and_sprints_toward_them_are_counted():
    colony = load(DEFAULT.parent / 'colony.toml')
    short = replace(colony, episode=replace(colony.episode, seconds=40.0),
                    flowers=replace(colony.flowers, every_min=1.0, every_max=2.0, count=4))
    assert run(short, POLICIES['greedy'], 4)['flowers']['max'] >= 1

    def tossing(world):
        greedy, coin = POLICIES['greedy'](world), np.random.default_rng(0)
        return lambda w: np.concatenate([greedy(w), coin.choice([-1.0, 1.0], (*w.alive.shape, 1))], -1)
    seen = run(short, tossing, 4)['actions']['sprint_flower']
    assert seen['ticks'] > 0 and 0 < seen['yes'] < 1
