import json
import threading
import urllib.request

import pytest

from terrarium import board, coordinator, jobs, worker

from test_jobs import result, spec, upload

REPORT = {'platform': 'Windows-10', 'slots': 1, 'trusted': False, 'version': 3, 'state': 'waiting',
          'reason': 'on battery', 'specs': {'os': 'Windows 10', 'cpu': 'Intel i7', 'cores': 8, 'memory_gb': 16,
                                            'gpus': [{'name': 'NVIDIA GeForce RTX 3060 Laptop GPU', 'memory_gb': 6}]}}


@pytest.fixture
def server(tmp_path, monkeypatch):
    root = tmp_path / 'coord'
    monkeypatch.setattr(board, 'OUTSIDE', tmp_path / 'board.toml')
    httpd = coordinator.serve(root, port=0, signers=None)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{httpd.server_address[1]}'
    tokens = coordinator.Tokens(root)
    clients = {name: jobs.Client(url, tokens.add(name, role))
               for name, role in (('admin', 'admin'), ('laptop', 'donor'), ('pod', 'rented'))}
    yield root, url, clients
    httpd.shutdown()


def get(url: str):
    with urllib.request.urlopen(url + '/api/board') as r:
        return r.headers, json.loads(r.read())


def test_the_board_shows_what_a_machine_did_and_what_it_is_but_not_what_its_owner_is_up_to(server, monkeypatch):
    root, url, c = server
    monkeypatch.setattr(jobs, 'verify', lambda *a: True)
    c['laptop'].json('POST', '/api/status', REPORT | {'hostname': 'friends-laptop', 'platform': 'x' * 500})
    upload(c['admin'], spec('b' * 12))
    c['laptop'].json('POST', '/api/claim', {})
    c['laptop'].json('PUT', f'/api/jobs/{"b" * 12}/result', result(f'20261026-120000-nbbb-{"b" * 12}'))
    headers, shown = get(url)
    assert headers['Access-Control-Allow-Origin'] == '*'
    assert headers['Cache-Control'] == f'public, max-age={coordinator.BOARD_TTL}'
    [laptop] = [m for m in shown['machines'] if m['name'] == 'laptop']
    assert laptop['kind'] == 'donor' and laptop['gpu'] == 'NVIDIA GeForce RTX 3060 Laptop GPU'
    assert laptop['jobs'] == 1 and laptop['samples'] == spec()['samples'] and laptop['last_active']
    assert shown['totals']['donor'] == {'machines': 1, 'samples': spec()['samples'], 'hours': laptop['hours']}
    text = json.dumps(shown)
    assert 'battery' not in text and 'waiting' not in text and 'friends-laptop' not in text
    assert 'admin' not in {m['name'] for m in shown['machines']}
    # River sees the whole report, cut down to the fields it knows
    kept = c['admin'].json('GET', '/api/workers')['laptop']['info']
    assert kept['state'] == 'waiting' and kept['specs']['cores'] == 8
    assert 'hostname' not in kept and len(kept['platform']) == board.TEXT


def test_a_report_is_kept_through_a_restart(server):
    root, _, c = server
    c['pod'].json('POST', '/api/status', REPORT)
    again = coordinator.Queue(root, signers=None)
    assert again.workers['pod']['info']['specs']['memory_gb'] == 16
    assert again.board()['machines'][0]['kind'] == 'rented'


def test_what_trained_outside_the_queue_is_added_by_name(server, monkeypatch):
    root, url, c = server
    monkeypatch.setattr(jobs, 'verify', lambda *a: True)
    (root.parent / 'board.toml').write_text(
        '[[machine]]\nname = "laptop"\nkind = "trusted"\ngpu = "Apple M3"\nsamples = 500\nhours = 1.5\nruns = 3\n'
        'last_active = "2026-10-20"\n'
        '[[machine]]\nname = "rented RTX 3060 12 GB"\nkind = "rented"\ngpu = "RTX 3060 12 GB"\nsamples = 9000\n'
        'hours = 4.0\nruns = 7\nlast_active = "2026-10-25"\ndollars = 1.5\n')
    c['laptop'].json('POST', '/api/status', REPORT)
    upload(c['admin'], spec('b' * 12))
    c['laptop'].json('POST', '/api/claim', {})
    c['laptop'].json('PUT', f'/api/jobs/{"b" * 12}/result', result(f'20261026-120000-nbbb-{"b" * 12}'))
    _, shown = get(url)
    rented, laptop = shown['machines']
    assert rented == {'name': 'rented RTX 3060 12 GB', 'kind': 'rented', 'gpu': 'RTX 3060 12 GB', 'samples': 9000,
                      'hours': 4.0, 'jobs': 7, 'last_active': '2026-10-25', 'dollars': 1.5}
    # the queue's own numbers for a machine it knows, plus the ledger's; the token decides its kind
    assert laptop['kind'] == 'donor' and laptop['samples'] == spec()['samples'] + 500 and laptop['jobs'] == 4
    assert laptop['last_active'] > '2026-10-20'
    assert shown['totals']['rented'] == {'machines': 1, 'samples': 9000, 'hours': 4.0, 'dollars': 1.5}



def test_my_own_machine_shows_as_mine_whatever_token_it_works_under():
    ledger = [{'name': 'river-m3', 'kind': 'admin', 'gpu': 'Apple M3', 'samples': 500, 'hours': 1.5, 'runs': 3,
               'last_active': '2026-10-20'}]
    shown = board.summary([], {'river-m3': {'role': 'trusted', 'seen': 0.0}}, {}, ledger=ledger)
    assert shown['machines'][0]['kind'] == 'admin' and shown['totals']['admin']['samples'] == 500
    assert shown['totals']['trusted']['machines'] == 0


def test_clean_keeps_known_fields_of_the_right_kinds():
    kept = board.clean({'slots': 2, 'trusted': 1, 'version': -1, 'state': 7, 'specs': {'cores': '8', 'gpus': ['x', {'name': 3}]}})
    assert kept == {'slots': 2, 'specs': {'os': None, 'cpu': None, 'cores': None, 'memory_gb': None,
                                             'gpus': [{'name': None, 'memory_gb': None}]}}


def test_a_worker_says_what_it_is_and_what_its_doing(tmp_path):
    w = worker.Worker(jobs.Client('http://127.0.0.1:1', 'x'), home=tmp_path, paused=True)
    info = w.info()
    assert info['state'] == 'paused' and set(info['specs']) == {'os', 'cpu', 'cores', 'memory_gb', 'gpus'}
    assert board.clean(info)['specs']['cores'] == info['specs']['cores']
    assert info['version'] == worker.VERSION


def test_how_hard_a_machine_trains_is_kept_for_river_and_never_on_the_board(server):
    root, url, c = server
    lately = {'samples_per_second': 2656, 'update_seconds': 9.06, 'gpu_busy_update': 0.41, 'gpu_busy_collect': True,
              'cpu_cores_collect': -3, 'whatever': 1, 'held_back': 'the update ' * 40}
    c['laptop'].json('POST', '/api/status', REPORT | {'usage': lately})
    kept = c['admin'].json('GET', '/api/workers')['laptop']['info']['usage']
    assert set(kept) == {'samples_per_second', 'update_seconds', 'gpu_busy_update', 'held_back'}
    assert len(kept['held_back']) == 300
    _, shown = get(url)
    assert 'update' not in json.dumps(shown)


def test_a_training_job_says_where_its_time_goes(tmp_path):
    task = worker.Task({'spec': {'id': 'j', 'name': 'n', 'batch': 'b', 'samples': 10}, 'sig': ''})
    task.run, task.state = tmp_path, 'training'
    assert task.usage() is None
    (tmp_path / 'run.json').write_text(json.dumps({'device': 'cuda', 'workers': 8}))
    rows = [{'samples': 32768 * i, 'samples_per_second': 2656, 'collect_seconds': 3.3, 'update_seconds': 9.1,
             'gpu_busy_update': 0.4} for i in range(1, 4)]
    (tmp_path / 'metrics.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    got = task.usage()
    assert got and got['update_seconds'] == 9.1 and 'waits on Python' in got['held_back']
    assert task.progress()['samples'] == 3 * 32768
