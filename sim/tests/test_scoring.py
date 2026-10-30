import numpy as np

from terrarium.games import against, labels, summary


def test_an_interval_holds_its_mean_and_narrows_with_more_episodes():
    rng = np.random.default_rng(3)
    few, many = rng.normal(5, 2, 16), rng.normal(5, 2, 1024)
    a, b = summary(few), summary(many)
    assert a['low'] <= a['mean'] <= a['high']
    assert b['high'] - b['low'] < (a['high'] - a['low']) / 4
    assert b['low'] < 5 < b['high']


def test_paired_episodes_tell_apart_what_unpaired_noise_would_hide():
    rng = np.random.default_rng(4)
    worlds = rng.normal(0, 5, 128)              # hard and easy worlds, shared by both players
    a, b = worlds + rng.normal(0, 0.2, 128), worlds + 0.5 + rng.normal(0, 0.2, 128)
    c = against(a, b)
    assert c['apart'] and c['difference'] > 0
    # the same gap with the worlds shuffled, as if each had played its own: lost in the worlds' spread
    assert not against(a, rng.permutation(b))['apart']
    assert against(a, a) == {'difference': 0.0, 'low': 0.0, 'high': 0.0, 'apart': False}


def test_brains_with_the_same_file_name_go_by_their_run():
    players = ['random', 'runs/20261030-1-none/checkpoints/00016.pt', 'runs/20261030-2-gru/checkpoints/00016.pt',
               'runs/20261030-2-gru/checkpoints/00016.pt wiped', 'brains/c1c16fc46934.pt',
               'runs/20261030-2-gru/checkpoints/00016.pt wiped every 3 s']
    assert labels(players) == {'random': 'random', players[1]: '20261030-1-none', players[2]: '20261030-2-gru',
                               players[3]: '20261030-2-gru wiped', players[4]: 'c1c16fc46934.pt',
                               players[5]: '20261030-2-gru wiped every 3 s'}


def test_perfect_memory_moves_on_when_the_berry_it_remembers_is_gone():
    """last_seen once waited for good where it last saw a berry, so it stood still whenever the next one landed out
    of sight: it found 35% in one-look peekaboo and walked 10 m a minute."""
    from terrarium.config import DEFAULT
    from terrarium.games import score
    got = score('peek', ['last_seen'], str(DEFAULT.parent / 'nursery-peek.toml'), episodes=4, processes=1)
    find = got['players']['last_seen']['find']
    assert np.mean(find['walked']) > 30 and np.mean(find['found']) > 0.5
