import threading
import time

import pytest

from terrarium import coordinator, jobs, pods
from terrarium.store import sha256


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'verify', lambda *a: True)
    root = tmp_path / 'coord'
    httpd = coordinator.serve(root, port=0, signers=None)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{httpd.server_address[1]}'
    tokens = coordinator.Tokens(root)
    yield url, {role: jobs.Client(url, tokens.add(role, role)) for role in coordinator.ROLES}
    httpd.shutdown()


def spec(id, on: str | None = 'rented', parent=None, added=1.0):
    return {'format': 1, 'id': id, 'batch': 'b', 'name': f'n{id[:3]}', 'added': added,
            'code': {'commit': 'c' * 40, 'bundle': None, 'overlay': None}, 'trusted': True,
            'world': sha256(b'w'), 'world_file': 'world.toml', 'train': sha256(b't'), 'train_file': 'train.toml',
            'parent': parent, 'seed': 0, 'samples': 64, 'on': on}


def upload(client, s):
    for data in (b'w', b't'):
        client.json('PUT', f'/api/blobs/{sha256(data)}', data)
    client.json('POST', '/api/jobs', {'spec': s, 'sig': 'sig'})


def test_the_pods_token_sees_the_rented_backlog_and_nothing_else(server):
    url, c = server
    upload(c['admin'], spec('a' * 12))
    upload(c['admin'], spec('b' * 12, parent={'job': 'a' * 12}, added=2))
    upload(c['admin'], spec('c' * 12, on=None, added=3))
    back = c['pods'].json('GET', '/api/pods')
    assert back['waiting'] == 1 and back['chained'] == 1 and back['pods'] == {}
    for method, path in (('GET', '/api/jobs'), ('POST', '/api/claim'), ('GET', f'/api/blobs/{sha256(b"w")}'),
                         ('POST', f'/api/jobs/{"a" * 12}/cancel')):
        assert c['pods'].call(method, path, {} if method == 'POST' else None)[0] == 404
    assert c['rented'].call('GET', '/api/pods')[0] == 404 and c['rented'].call('POST', '/api/pods/pod-x', {})[0] == 404


def test_a_pod_token_is_rented_short_lived_and_dropped_with_its_job(server):
    url, c = server
    upload(c['admin'], spec('a' * 12))
    assert c['pods'].call('POST', '/api/pods/river-mac', {})[0] == 400
    assert c['pods'].call('POST', '/api/pods/pod-1', {'hours': 13})[0] == 400
    made = c['pods'].json('POST', '/api/pods/pod-1', {'hours': 1})
    assert made['until'] > time.time() + 3500
    pod = jobs.Client(url, made['token'])
    assert pod.json('POST', '/api/claim', {})['spec']['id'] == 'a' * 12
    back = c['pods'].json('GET', '/api/pods')
    assert back['waiting'] == 0 and back['pods']['pod-1']['job'] == 'a' * 12 and back['pods']['pod-1']['seen']
    assert c['pods'].call('POST', '/api/pods/pod-1', {})[0] == 409
    assert c['pods'].json('POST', '/api/pods/pod-1/gone', {}) == {'returned': ['a' * 12]}
    assert pod.call('POST', '/api/claim', {})[0] == 401
    assert c['pods'].json('GET', '/api/pods')['waiting'] == 1
    assert c['pods'].call('POST', '/api/pods/trusted/gone', {})[0] == 403


def test_a_token_past_its_time_is_no_token(tmp_path):
    tokens = coordinator.Tokens(tmp_path)
    old, fresh = tokens.add('pod-old', 'rented', time.time() - 1), tokens.add('pod-new', 'rented', time.time() + 60)
    assert tokens.who(old) is None
    assert (tokens.who(fresh) or {}).get('name') == 'pod-new'


class Fake:
    """A provider that rents instantly and remembers what it has."""

    def __init__(self, name, dph=0.2, stock=True):
        self.name, self.dph, self.stock = name, dph, stock
        self.pods: dict[str, str] = {}
        self.scripts: list[str] = []
        self.destroyed: list[str] = []

    def live(self):
        return dict(self.pods)

    def rent(self, label, gpus, max_dph, script, avoid=()):
        self.avoided = set(avoid)
        if not self.stock or self.dph > max_dph:
            return None
        id = str(100 + len(self.scripts))
        self.pods[id] = label
        self.scripts.append(script)
        return id, self.dph, {'machine': f'm{id}', 'setup': 0.02}

    def destroy(self, id):
        self.pods.pop(id, None)
        self.destroyed.append(id)


class Clock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t


def manager(tmp_path, c, settings='cap_usd_day = 5.0\nmax_pods = 2\nhours = 6.0\n', **fakes):
    state = tmp_path / 'state'
    state.mkdir(exist_ok=True)
    if settings is not None:
        (state / 'pods.toml').write_text(settings)
    provs = fakes or {'vast': Fake('vast'), 'runpod': Fake('runpod')}
    clock = Clock()
    m = pods.Manager(state, lambda method, path, body=None: c['pods'].json(method, path, body), provs,
                     lambda cfg: 'f' * 40, now=clock)
    return m, provs, clock


def test_nothing_is_rented_without_settings_or_work(server, tmp_path):
    url, c = server
    m, provs, _ = manager(tmp_path, c, settings=None)
    upload(c['admin'], spec('a' * 12))
    assert m.tick()['rented'] is None and not provs['vast'].pods
    (tmp_path / 'b').mkdir()
    m2, provs2, _ = manager(tmp_path / 'b', c)
    c['admin'].json('POST', f'/api/jobs/{"a" * 12}/cancel', {})
    assert m2.tick()['rented'] is None and not provs2['vast'].pods


def test_a_job_waiting_rents_one_pod_that_boots_with_its_own_token(server, tmp_path):
    url, c = server
    m, provs, clock = manager(tmp_path, c)
    upload(c['admin'], spec('a' * 12))
    status = m.tick()
    assert status['rented'] and len(provs['vast'].pods) == 1 and not provs['runpod'].pods
    script = provs['vast'].scripts[0]
    assert 'f' * 40 in script and 'sleep 21600' in script and '--trusted --anytime' in script
    token = script.split("printf %s '")[1].split("'")[0]
    assert jobs.Client(url, token).json('POST', '/api/claim', {})['spec']['id'] == 'a' * 12
    clock.t += 60
    assert m.tick()['rented'] is None and len(provs['vast'].pods) == 1


def test_the_next_provider_is_tried_when_the_first_has_nothing(server, tmp_path):
    url, c = server
    m, provs, _ = manager(tmp_path, c, vast=Fake('vast', stock=False), runpod=Fake('runpod'))
    upload(c['admin'], spec('a' * 12))
    m.tick()
    assert len(provs['runpod'].pods) == 1 and m.ledger.live()[0]['provider'] == 'runpod'


def test_a_pod_that_never_says_hello_goes_and_so_does_its_token(server, tmp_path):
    url, c = server
    m, provs, clock = manager(tmp_path, c)
    upload(c['admin'], spec('a' * 12))
    m.tick()
    token = provs['vast'].scripts[0].split("printf %s '")[1].split("'")[0]
    clock.t += 16 * 60
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(time, 'time', clock)
        m.tick()
    assert provs['vast'].destroyed == ['100'] and m.ledger.db.execute('select why from pods').fetchone()[0] == \
        'no hello in 15 min'
    assert jobs.Client(url, token).call('POST', '/api/claim', {})[0] == 401


def test_a_pod_with_nothing_to_do_goes_after_a_few_idle_minutes(server, tmp_path):
    url, c = server
    m, provs, clock = manager(tmp_path, c)
    upload(c['admin'], spec('a' * 12))
    m.tick()
    pod = jobs.Client(url, provs['vast'].scripts[0].split("printf %s '")[1].split("'")[0])
    pod.json('POST', '/api/hello', {})
    c['admin'].json('POST', f'/api/jobs/{"a" * 12}/cancel', {})
    clock.t = time.time()
    m.tick()
    assert not provs['vast'].destroyed
    clock.t += 6 * 60
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(time, 'time', lambda: clock.t - 5 * 60)
        pod.json('POST', '/api/status', {})
    m.tick()
    assert provs['vast'].destroyed == ['100']
    assert m.ledger.db.execute('select why from pods').fetchone()[0] == 'idle for 5 min'


def test_orphans_are_destroyed_and_pods_gone_at_the_provider_are_marked_gone(server, tmp_path):
    url, c = server
    m, provs, clock = manager(tmp_path, c)
    provs['runpod'].pods['zzz'] = 'terrarium-q-pod-left-over'
    upload(c['admin'], spec('a' * 12))
    status = m.tick()
    assert status['orphans'] == 1 and provs['runpod'].destroyed == ['zzz']
    provs['vast'].pods.clear()
    m.tick()
    assert m.ledger.db.execute('select why from pods').fetchone()[0] == 'gone at the provider'


def test_the_days_cap_counts_running_pods_and_a_whole_new_one(server, tmp_path):
    url, c = server
    m, provs, clock = manager(tmp_path, c, settings='cap_usd_day = 1.5\nmax_pods = 2\nhours = 6.0\nmax_dph = 0.3\n')
    upload(c['admin'], spec('a' * 12))
    m.tick()
    assert not provs['vast'].pods
    m.ledger.add('pod-old', 'vast', '1', 0.25, clock.t - 3600 * 30, 'x')
    m.ledger.gone('pod-old', clock.t - 3600 * 20, 'done')
    assert m.ledger.spent(clock.t) == pytest.approx(0.25 * 4)


def test_settings_refuse_a_typo(tmp_path):
    (tmp_path / 'pods.toml').write_text('cap_usd_dya = 3.0\n')
    with pytest.raises(ValueError, match='cap_usd_dya'):
        pods.settings(tmp_path)


def test_runpod_rents_the_cheapest_card_in_stock_in_either_cloud(monkeypatch):
    stock = {'NVIDIA RTX A4500': ({'uninterruptablePrice': 0.19, 'stockStatus': 'Low'}, {'uninterruptablePrice': 0.25, 'stockStatus': 'High'}),
             'NVIDIA RTX A4000': ({'uninterruptablePrice': None, 'stockStatus': None}, {'uninterruptablePrice': 0.17, 'stockStatus': 'Low'}),
             'NVIDIA GeForce RTX 3090': ({'uninterruptablePrice': 0.22, 'stockStatus': 'Low'}, None)}
    asked = []

    def api(self, query, variables=None):
        if query.startswith('query'):
            return {'gpuTypes': [{'id': g, 'COMMUNITY': c, 'SECURE': s} for g, (c, s) in stock.items() if g in variables['ids']]}
        asked.append(variables['i'])
        if variables['i']['gpuTypeId'] == 'NVIDIA RTX A4000':
            raise RuntimeError('There are no longer any instances available with the requested specifications')
        return {'podFindAndDeployOnDemand': {'id': 'p1', 'costPerHr': 0.19}}

    monkeypatch.setattr(pods.RunPod, 'api', api)
    r = pods.RunPod('key')
    cards = [*stock, 'A4500']
    assert r.offers(cards, 0.24) == [(0.17, 'NVIDIA RTX A4000', 'SECURE'), (0.19, 'NVIDIA RTX A4500', 'COMMUNITY'),
                                    (0.22, 'NVIDIA GeForce RTX 3090', 'COMMUNITY')]
    # the A4000 sells out between asking and renting, so the next cheapest goes
    assert r.rent('terrarium-q-x', cards, 0.24, 'echo hi') == ('p1', 0.19, {})
    assert [(i['gpuTypeId'], i['cloudType']) for i in asked] == [('NVIDIA RTX A4000', 'SECURE'), ('NVIDIA RTX A4500', 'COMMUNITY')]


def test_a_pod_whose_jobs_keep_failing_goes_and_its_machine_is_skipped_for_the_day(server, tmp_path):
    url, c = server
    m, provs, clock = manager(tmp_path, c)
    upload(c['admin'], spec('a' * 12))
    m.tick()
    script = provs['vast'].scripts[0]
    pod = jobs.Client(url, script.split("printf %s '")[1].split("'")[0])
    for _ in range(2):
        id = pod.json('POST', '/api/claim', {})['spec']['id']
        pod.json('POST', f'/api/jobs/{id}/fail', {'error': 'uv sync returned non-zero exit status 1'})
    assert c['pods'].json('GET', '/api/pods')['pods'][m.ledger.live()[0]['name']] | {'seen': 1} == \
        {'until': pytest.approx(clock.t + 6 * 3600, abs=60), 'seen': 1, 'job': None, 'failed': 2, 'failed_brain': 0, 'finished': 0}
    clock.t += 60
    m.tick()
    assert provs['vast'].destroyed == ['100'] and m.ledger.bad(clock.t) == {'m100'}
    # its setup download counts towards the day's spend
    assert m.ledger.spent(clock.t) == pytest.approx(0.2 * 60 / 3600 + 0.02, abs=1e-3)
    upload(c['admin'], spec('b' * 12, added=2))
    m.tick()
    assert provs['vast'].avoided == {'m100'} and len(provs['vast'].pods) == 1
    clock.t += 25 * 3600
    assert m.ledger.bad(clock.t) == set()
