import json

import numpy as np
import pytest

from terrarium import replay
from terrarium.brain import SHAPE, Brain, save
from terrarium.kids import DRAIN, EASE, FILL, LITTLE, MODES, REGROW, TURBO, Catch


@pytest.fixture
def brain(tmp_path):
    path = tmp_path / 'brain.pt'
    save(Brain(**SHAPE), path)
    return path


def put(game, slot):
    """The runner in that slot, moved to touch you on your right."""
    w = game.world
    x, y = w.pos[0, game.slot]
    w.physics.bodies[0][slot].position = (float(x + 2 * w.cfg.creature.radius + 0.01), float(y))
    w.physics.read()


def touch(game, slot):
    """Step until the runner in that slot is caught, holding it beside you."""
    for _ in range(40):
        put(game, slot)
        game.tag.step()
        if game.tag.it[0] != game.slot:
            game.caught(int(game.tag.it[0]))
            return
    raise AssertionError('never caught')


@pytest.mark.parametrize('mode,level', [(m, i + 1) for m, levels in MODES.items() for i in range(len(levels))])
def test_you_start_it_with_the_level_s_runners(brain, mode, level):
    game = Catch(mode, brain, 1, level=level)
    setting = MODES[mode][level - 1]
    w = game.world
    assert game.tag.it[0] == game.slot
    you = next(c for c in game.first['creatures'] if c['id'] == game.you)
    assert you['signal'] == 0
    assert w.alive[0].sum() == setting.runners + 1
    assert w.episode_ticks == round(setting.seconds * w.cfg.tick_hz)
    assert w.cfg.tag.speed == setting.you and game.score()['level'] == level


def test_a_catch_keeps_you_it_and_the_caught_one_dizzy_and_safe(brain):
    game = Catch('little', brain, 2)
    runner = game.slot + 1
    touch(game, runner)
    assert game.tag.it[0] == game.slot
    assert len(game.catches) == 1 and game.catches[0]['id'] == int(game.world.creature_id[0, runner])
    assert runner in game.dizzy
    # still touching it: it can't be caught again until its safe time is up
    w = game.world
    for _ in range(round(LITTLE.safe * w.cfg.tick_hz) - 2):
        put(game, runner)
        game.tag.step()
        assert game.tag.it[0] == game.slot


def test_a_caught_one_tumbles_away_then_spins_on_the_spot(brain):
    game = Catch('little', brain, 3)
    w = game.world
    runner = game.slot + 1
    touch(game, runner)
    before = np.hypot(*(w.pos[0, runner] - w.pos[0, game.slot]))
    sent = []
    step = w.step
    w.step = lambda actions: (sent.append(actions[0].copy()), step(actions))
    game.step(round(LITTLE.dizzy * game.hz) - 1, 0.0, 0.0, [])
    assert sent[0][runner, 0] == 1 and sent[0][runner, 1] == 0
    assert sent[-1][runner, 0] == 0 and sent[-1][runner, 1] == 1
    assert np.hypot(*(w.pos[0, runner] - w.pos[0, game.slot])) > before + 1.5


def test_the_runners_slow_without_catches_and_speed_up_on_quick_ones(brain):
    mode = LITTLE
    game = Catch('little', brain, 4)
    hz = game.hz
    start = game.pace
    for _ in range(round((mode.gap + 3) * hz)):
        game.ticks += 1
        game.adjust()
    assert game.pace == pytest.approx(start - 3 * EASE, abs=EASE / 2)
    # never slower than the mode allows
    for _ in range(round(200 * hz)):
        game.ticks += 1
        game.adjust()
    assert game.pace == mode.slowest
    slow = game.pace
    touch(game, game.slot + 1)
    game.ticks += 1
    touch(game, game.slot + 2)
    assert game.pace > slow
    for i in range(200):
        game.ticks += 1
        game.dizzy.clear()
        game.tag.back[0] = -1
        touch(game, game.slot + 1 + i % mode.runners)
    assert game.pace == mode.fastest


def test_the_runners_go_at_the_game_s_pace(brain):
    game = Catch('little', brain, 5)
    game.pace = 0.5
    sent = []
    step = game.world.step
    game.act = lambda w: np.ones((1, len(w.colony), 7))
    game.world.step = lambda actions: (sent.append(actions[0].copy()), step(actions))
    game.step(1, 1.0, 0.0, [])
    runners = [s for s in range(len(game.world.colony)) if s != game.slot and game.world.alive[0, s]]
    assert np.allclose(sent[0][runners, 0], 0.5) and sent[0][game.slot, 0] == 1.0


def test_a_game_kept_leaves_its_replay_and_one_line(brain, tmp_path):
    keep = tmp_path / 'kept'
    game = Catch('little', brain, 6, keep, device='mouse')
    game.step(10, 1.0, 0.3, [])
    # walking about may have caught one already
    game.tag.back[0] = -1
    touch(game, game.slot + 1)
    game.close('quit')
    game.close('idle')
    lines = (keep / 'plays.jsonl').read_text().splitlines()
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert line['why'] == 'quit' and line['mode'] == 'little' and line['device'] == 'mouse'
    assert line['catches'] == len(game.catches) >= 1
    assert line['played'] == 0.5
    head, frames = replay.read(game.file)
    assert head['source']['kids']['mode'] == 'little' and len(frames) == 11


def test_a_game_played_to_the_end_closes_itself(brain, tmp_path):
    game = Catch('little', brain, 7, tmp_path)
    while not game.score()['over']:
        game.step(10, 0.5, 0.2, [])
    assert game.closed
    line = json.loads((tmp_path / 'plays.jsonl').read_text())
    assert line['why'] == 'over' and line['played'] == LITTLE.seconds


def test_snacks_fill_turbo_and_sprint_runs_on_it(brain):
    game = Catch('little', brain, 4)
    w, hz = game.world, game.hz
    assert len(game.snacks) == LITTLE.snacks and game.turbo == 0
    # no bar, no turbo: holding sprint does nothing
    game.step(1, 1.0, 0.0, ['sprint'])
    assert game.boosted == 0
    snack = game.snacks[0]
    w.physics.bodies[0][game.slot].position = (snack['x'], snack['y'])
    w.physics.read()
    game.step(1, 0.0, 0.0, [])
    assert snack not in game.snacks and game.eaten == 1 and game.turbo == pytest.approx(FILL)
    frames = game.step(4, 1.0, 0.0, ['sprint'])
    assert game.boosted == 4 and game.turbo == pytest.approx(FILL - 4 * DRAIN / hz)
    you = next(c for c in frames[-1]['creatures'] if c['id'] == game.you)
    assert you['sprinting'] == 1
    assert w.cfg.sprint.speed == TURBO and not w.cfg.sprint.on
    # the runners never sprint
    others = np.arange(w.sprinting.shape[1]) != game.slot
    assert not w.sprinting[0, others].any()
    # an eaten one comes back somewhere else
    game.step(round(REGROW * hz) + 1, 0.0, 0.0, [])
    assert len(game.snacks) == LITTLE.snacks and all(s['kind'] in ('berry', 'seaweed') for s in game.snacks)


def test_big_keeps_its_own_sprint_and_has_no_snacks(brain):
    game = Catch('big', brain, 5)
    assert game.snacks == [] and game.world.cfg.sprint.on
    game.step(1, 1.0, 0.0, ['sprint'])
    assert game.world.sprinting[0, game.slot] > 0 and game.boosted == 0
