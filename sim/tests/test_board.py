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
def server(tmp_path):
    root = tmp_path / 'coord'
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
    [laptop] = [m for m in shown['machines'] if m['name'] == 'laptop']
    assert laptop['kind'] == 'lent' and laptop['gpu'] == 'NVIDIA GeForce RTX 3060 Laptop GPU'
    assert laptop['jobs'] == 1 and laptop['samples'] == spec()['samples'] and laptop['last_active']
    assert shown['totals']['lent'] == {'machines': 1, 'samples': spec()['samples'], 'hours': laptop['hours']}
    text = json.dumps(shown)
    assert 'battery' not in text and 'waiting' not in text and 'friends-laptop' not in text and 'admin' not in text
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
