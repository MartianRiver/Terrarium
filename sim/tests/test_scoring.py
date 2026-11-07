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


def test_peekaboo_notes_are_wiped_once_as_the_berry_hides():
    from terrarium import config
    from terrarium.games import hides
    from terrarium.world import World
    cfg = config.load(config.DEFAULT.parent / 'nursery-peek.toml')
    w = World(cfg, 2, 0)
    w.reset(np.ones(2, bool))
    check = hides(w)
    fired = []
    for _ in range(int(3 * cfg.tick_hz)):
        w.step(np.zeros((*w.alive.shape, 2)))
        hit = check(w)
        assert hit.shape == w.alive.shape and (hit.all(1) | ~hit.any(1)).all()
        fired.append(hit[:, 0])
    fired = np.array(fired)
    # in sight for `show` seconds, then hidden: one wipe each, at that tick, and none while it stays hidden
    assert (fired.sum(0) == 1).all()
    assert abs(fired.argmax(0) / cfg.tick_hz - cfg.peek.show).max() < 0.1


def test_a_maze_wipe_comes_with_each_new_room():
    from terrarium import config
    from terrarium.games import new_room
    from terrarium.world import World
    cfg = config.load(config.DEFAULT.parent / 'nursery-maze-3.toml')
    w = World(cfg, 1, 0)
    w.reset(np.ones(1, bool))
    check = new_room(w)
    assert check(w).all()  # nowhere before the first choice
    assert not check(w).any()
    size, n = cfg.arena.size, cfg.arena.maze
    w.pos[0, 0] = w.pos[0, 0] + [size / n, 0]
    hit = check(w)
    assert hit[0, 0] and not hit[0, 1:].any()


def test_a_wipe_on_every_choice_is_the_same_as_wiped(tmp_path):
    import json
    from dataclasses import replace
    import torch
    from terrarium import config
    from terrarium.brain import SHAPE, Brain, save
    from terrarium.evals import brain_policy, run
    cfg = config.load(config.DEFAULT.parent / 'solo.toml')
    cfg = replace(cfg, episode=replace(cfg.episode, seconds=3.0))
    # a random brain whose turning hangs on its memory: with some seeds it turns the same either way
    torch.manual_seed(2)
    brain = Brain(**SHAPE).with_memory(8)
    with torch.no_grad():
        for q in brain.parameters():
            q.add_(0.3 * torch.randn_like(q))
    save(brain, tmp_path / 'b.pt')
    always = lambda world: (lambda w: np.ones(w.alive.shape, bool))
    on = run(cfg, brain_policy(tmp_path / 'b.pt', wipe_on=always), episodes=2)
    wiped = run(cfg, brain_policy(tmp_path / 'b.pt', wiped=True), episodes=2)
    kept = run(cfg, brain_policy(tmp_path / 'b.pt'), episodes=2)
    assert json.dumps(on, sort_keys=True) == json.dumps(wiped, sort_keys=True)
    assert json.dumps(on, sort_keys=True) != json.dumps(kept, sort_keys=True)
