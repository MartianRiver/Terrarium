import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from terrarium import invites
from terrarium.playserve import Hosted, handler
from terrarium.serve import Runs

from test_serve import make_run

KEY = 'test-key'


def test_an_invite_says_whose_it_is_until_it_runs_out():
    code = invites.make(KEY, 'Sam', days=7, now=1000.0)
    assert invites.check(KEY, code, now=1000.0 + 6.9 * 86400) == 'Sam'
    with pytest.raises(invites.BadInvite, match='run out'):
        invites.check(KEY, code, now=1000.0 + 7.1 * 86400)


def test_an_invite_made_with_another_key_or_changed_is_refused():
    code = invites.make(KEY, 'Sam', now=1000.0)
    body, sig = code.split('.')
    longer = invites._b64(json.dumps({'n': 'Sam', 'e': 10**12}).encode())
    for bad in [invites.make('other', 'Sam', now=1000.0), f'{longer}.{sig}', body, '', 'a.b', code + 'x']:
        with pytest.raises(invites.BadInvite):
            invites.check(KEY, bad, now=1000.0)


@pytest.fixture
def server(tmp_path):
    make_run(tmp_path, 'run', '2026-10-28T10:00:00+1100', checkpoints=[32768])
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(Runs(tmp_path), Hosted(total=2, each=1), KEY))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_game_needs_an_invite_and_plays_with_one(server):
    assert post(f'{server}/api/play', {})[0] == 403
    assert post(f'{server}/api/play', {'invite': 'nope.nope'})[0] == 403
    status, game = post(f'{server}/api/play', {'invite': invites.make(KEY, 'Sam')})
    assert status == 200 and game['frame'] and 'you' in game
    status, more = post(f"{server}/api/play/{game['game']}", {'ticks': 2, 'thrust': 1})
    assert status == 200 and len(more['frames']) == 2


def test_full_turns_new_games_away_and_one_invite_holds_only_its_share(server):
    sam, alex, kim = (invites.make(KEY, n) for n in ('Sam', 'Alex', 'Kim'))
    first = post(f'{server}/api/play', {'invite': sam})[1]['game']
    # Sam reloading the page: the old game goes, the new one takes its seat
    second = post(f'{server}/api/play', {'invite': sam})[1]['game']
    assert post(f'{server}/api/play/{first}', {})[0] == 404
    assert post(f'{server}/api/play/{second}', {})[0] == 200
    assert post(f'{server}/api/play', {'invite': alex})[0] == 200
    status, said = post(f'{server}/api/play', {'invite': kim})
    assert status == 503 and 'seat' in said['error']


def test_a_game_cant_be_stepped_much_faster_than_its_clock(server):
    game = post(f'{server}/api/play', {'invite': invites.make(KEY, 'Sam')})[1]['game']
    start = time.monotonic()
    for _ in range(5):
        post(f'{server}/api/play/{game}', {'ticks': 10})
    # 50 ticks at 20 a second, at most twice as fast: 1.25 s, less the first reply's head start
    assert time.monotonic() - start > 0.9
