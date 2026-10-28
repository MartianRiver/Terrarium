import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from terrarium.brain import SHAPE, Brain, save
from terrarium.config import DEFAULT, load
from terrarium.play import Game
from terrarium.schema import ACTIONS
from terrarium.serve import Runs, handler

from test_serve import make_run

COLONY = load(DEFAULT.parent / 'colony.toml')


@pytest.fixture
def brain(tmp_path):
    path = tmp_path / 'brain.pt'
    save(Brain(**SHAPE), path)
    return path


def test_yours_goes_where_you_steer_and_the_rest_are_the_brains(brain):
    still, walking = Game(COLONY, brain, 3, 'test'), Game(COLONY, brain, 3, 'test')
    start = walking.world.pos[0, walking.slot].copy()
    still.step(20, 0.0, 0.0, [])
    walking.step(20, 1.0, 0.0, [])
    moved = lambda g: np.hypot(*(g.world.pos[0, g.slot] - start))
    assert moved(walking) > 1.0 and moved(still) < 0.3
    # everyone else played the same in both: your own steering is the only difference (ids, not slots, in replays)
    others = [i for i in range(len(still.world.colony)) if i != still.slot]
    assert np.abs(still.world.pos[0, others] - walking.world.pos[0, others]).max() < 1.0


def test_only_the_actions_this_world_has_are_yours(brain):
    game = Game(load(DEFAULT.parent / 'night.toml'), brain, 0, 'test')
    assert 'grab' not in game.controls
    sent = []
    game.world.step = lambda actions: sent.append(actions[0, game.slot].copy())
    game.step(1, 0.5, -0.5, ['grab', 'sprint', 'nonsense'])
    mine = sent[0]
    assert mine[0] == 0.5 and mine[1] == -0.5 and mine[ACTIONS.index('grab')] == -1
    assert mine[ACTIONS.index('sprint')] == (1 if 'sprint' in game.controls else -1)


def test_once_yours_dies_the_brain_has_its_place_and_you_watch_to_the_end(brain):
    game = Game(COLONY, brain, 0, 'test')
    game.world.energy[0, game.slot] = 1e-6
    game.step(2, 0.0, 0.0, [])
    score = game.score()
    assert not game.playing and not score['you']['alive'] and not score['over']
    assert score['you']['seconds'] <= 0.1 and score['brain']['seconds'] > 0


def test_the_api_starts_a_game_steps_it_and_refuses_what_it_cant_use(tmp_path):
    make_run(tmp_path, 'run', '2026-10-28T10:00:00+1100', checkpoints=[32768])
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(Runs(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/api/play'

    def post(url, body):
        req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    try:
        got = post(base, {'seed': 4})
        assert got['label'] == 'run/00000032768.pt' and got['you'] == got['frame']['creatures'][0]['id']
        step = post(f'{base}/{got["game"]}', {'ticks': 3, 'thrust': 1, 'turn': 0, 'yes': []})
        assert [f['tick'] for f in step['frames']] == [1, 2, 3] and step['score']['you']['alive']
        for url, body, code in ((f'{base}/{got["game"]}', {'thrust': 'fast'}, 400),
                                (f'{base}/{got["game"]}', {'yes': 'sprint'}, 400),
                                (f'{base}/nobody', {}, 404), (base, {'run': 'missing'}, 404)):
            with pytest.raises(urllib.error.HTTPError) as e:
                post(url, body)
            assert e.value.code == code
    finally:
        server.shutdown()
