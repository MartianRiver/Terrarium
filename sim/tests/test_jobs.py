import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading

import pytest

from terrarium import coordinator, jobs, snapshot, worker
from terrarium.store import LEASE, Gone, Store, sha256

needs_ssh = pytest.mark.skipif(not shutil.which('ssh-keygen'), reason='no ssh-keygen')


@pytest.fixture(autouse=True)
def own_repos_only(monkeypatch):
    # under a git hook GIT_DIR points at the real repo, and git init there marked it bare
    for name in [k for k in os.environ if k.startswith('GIT_')]:
        monkeypatch.delenv(name)


def git(repo, *args):
    subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A small repo laid out like this one: code under sim/, a remote-tracking next."""
    repo = tmp_path / 'repo'
    (repo / 'sim').mkdir(parents=True)
    (repo / 'sim' / 'a.py').write_text('a = 1\n')
    (repo / 'sim' / 'gone.py').write_text('gone = 1\n')
    (repo / 'sim' / 'world.toml').write_text('size = 8\n')
    (repo / 'sim' / 'train.toml').write_text('[ppo]\nsamples = 64\n')
    (repo / '.gitignore').write_text('runs/\n')
    git(repo, 'init', '-q', '-b', 'next')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'one', '--allow-empty')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'two')
    git(repo, 'update-ref', 'refs/remotes/origin/next', 'HEAD')
    return repo


@pytest.fixture
def key(tmp_path):
    key = tmp_path / 'key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    signers = tmp_path / 'allowed_signers'
    signers.write_text(f'{jobs.PRINCIPAL} namespaces="{jobs.NAMESPACE}" {(tmp_path / "key.pub").read_text()}')
    return key, signers


def spec(id='a' * 12, trusted=False, parent=None, added=1.0, overlay=None, on=None):
    return {'format': 1, 'id': id, 'batch': 'b', 'name': f'n{id[:3]}', 'added': added,
            'code': {'commit': 'c' * 40, 'bundle': None, 'overlay': overlay}, 'trusted': trusted,
            'world': sha256(b'w'), 'world_file': 'world.toml', 'train': sha256(b't'), 'train_file': 'train.toml',
            'parent': parent, 'seed': 0, 'samples': 64, 'on': on}


def result(name='20261024-120000-run', checkpoint='00000000064.pt', weights=b'brain') -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for path, data in [(f'{name}/run.json', json.dumps({'checkpoint': checkpoint}).encode()),
                           (f'{name}/checkpoints/{checkpoint}', weights), (f'{name}/evals.json', b'{}')]:
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def store(tmp_path) -> Store:
    s = Store(tmp_path / 'state')
    s.put(b'w')
    s.put(b't')
    return s


def claimed(s: Store, worker: str, trusted: bool, now: float | None = None, role: str | None = None) -> dict:
    job = s.claim(worker, trusted, now, role)
    assert job is not None
    return job


def test_jobs_go_out_oldest_first_and_trusted_ones_only_to_trusted_workers(tmp_path):
    s = store(tmp_path)
    s.add(spec('a' * 12, trusted=True, added=1), 'sig')
    s.add(spec('b' * 12, added=2), 'sig')
    assert claimed(s, 'donor', trusted=False)['spec']['id'] == 'b' * 12
    assert s.claim('donor', trusted=False) is None
    assert claimed(s, 'mac', trusted=True)['spec']['id'] == 'a' * 12


def test_a_job_kept_to_rented_machines_only_goes_to_one(tmp_path):
    s = store(tmp_path)
    s.add(spec('a' * 12, trusted=True, on='rented'), 'sig')
    assert s.claim('mac', True, role='trusted') is None
    assert claimed(s, 'pod', True, role='rented')['spec']['id'] == 'a' * 12
    for bad in ('mac', 'admin'):
        with pytest.raises(jobs.BadJob, match='bad on'):
            jobs.check(spec(on=bad))
    with pytest.raises(jobs.BadJob, match='donor'):
        jobs.check(spec(trusted=True, on='donor'))


def test_a_job_waits_for_its_parent_job_and_gets_its_final_checkpoint(tmp_path):
    s = store(tmp_path)
    s.add(spec('a' * 12, added=1), 'sig')
    s.add(spec('b' * 12, parent={'job': 'a' * 12}, added=2), 'sig')
    first = claimed(s, 'mac', True)
    assert first['spec']['id'] == 'a' * 12 and s.claim('pod', True) is None
    s.finish('a' * 12, 'mac', result(weights=b'final brain'))
    second = claimed(s, 'pod', True)
    assert second['spec']['id'] == 'b' * 12 and s.get(s.parent_blob(second) or '') == b'final brain'


def test_a_lost_worker_lets_the_job_go_once_then_it_fails(tmp_path):
    s = store(tmp_path)
    s.add(spec(), 'sig')
    s.claim('pod1', True, now=100)
    s.beat('a' * 12, 'pod1', {'samples': 32}, now=200)
    assert s.claim('pod2', True, now=200 + LEASE - 1) is None
    assert claimed(s, 'pod2', True, now=200 + LEASE + 1)['attempts'] == 2
    with pytest.raises(Gone):
        s.beat('a' * 12, 'pod1', now=200 + LEASE + 2)
    assert s.claim('pod3', True, now=10_000) is None
    assert s.read('a' * 12)['state'] == 'failed'
    s.retry('a' * 12)
    assert claimed(s, 'pod3', True, now=10_001)['attempts'] == 1


def test_giving_a_job_back_is_not_an_attempt(tmp_path):
    s = store(tmp_path)
    s.add(spec(), 'sig')
    for _ in range(3):
        s.claim('mac', True)
        s.give_back('a' * 12, 'mac')
    job = s.read('a' * 12)
    assert job['state'] == 'pending' and job['attempts'] == 0


def test_a_restarted_worker_hands_back_what_it_held(tmp_path):
    s = store(tmp_path)
    s.add(spec('a' * 12, added=1), 'sig')
    s.add(spec('b' * 12, added=2), 'sig')
    claimed(s, 'mac', True)
    claimed(s, 'pod', True)
    assert s.restarted('mac') == ['a' * 12]
    assert [(j['state'], j['attempts']) for j in s.all()] == [('pending', 0), ('running', 1)]


def test_a_late_result_counts_unless_someone_else_has_the_job(tmp_path):
    s = store(tmp_path)
    s.add(spec(), 'sig')
    s.claim('slow', True, now=100)
    s.expire(100 + LEASE + 1)
    s.finish('a' * 12, 'slow', result())
    assert s.read('a' * 12)['state'] == 'done'
    with pytest.raises(Gone):
        s.finish('a' * 12, 'slow', result())

    s.add(spec('b' * 12), 'sig')
    s.claim('slow', True, now=100)
    s.claim('fast', True, now=100 + LEASE + 1)
    with pytest.raises(Gone):
        s.finish('b' * 12, 'slow', result())
    with pytest.raises(Gone):
        s.finish('b' * 12, 'stranger', result())


def test_a_result_without_its_final_checkpoint_is_refused(tmp_path):
    s = store(tmp_path)
    s.add(spec(), 'sig')
    s.claim('mac', True)
    with pytest.raises(ValueError):
        s.finish('a' * 12, 'mac', result(checkpoint='../../etc.pt'))
    assert s.read('a' * 12)['state'] == 'running'


def test_check_refuses_what_add_would_never_make():
    jobs.check(spec())
    for bad in [spec() | {'id': '../x'}, spec() | {'name': 'a/b'}, spec(overlay=sha256(b'o')),
                spec() | {'parent': {'blob': 'x', 'file': 'p.pt'}}, spec() | {'format': 2}, spec() | {'seed': 's'}]:
        with pytest.raises(jobs.BadJob):
            jobs.check(bad)


@needs_ssh
def test_a_signed_spec_verifies_and_any_change_breaks_it(key):
    k, signers = key
    s = spec()
    sig = jobs.sign(s, k)
    assert jobs.verify(s, sig, signers)
    assert not jobs.verify(s | {'seed': 1}, sig, signers)
    assert not jobs.verify(s | {'code': s['code'] | {'commit': 'd' * 40}}, sig, signers)


def test_an_overlay_rebuilds_the_dirty_tree_on_top_of_the_commit(repo, tmp_path):
    (repo / 'sim' / 'a.py').write_text('a = 2\n')
    (repo / 'sim' / 'new').mkdir()
    (repo / 'sim' / 'new' / 'b.py').write_text('b = 1\n')
    (repo / 'sim' / 'gone.py').unlink()
    (repo / 'runs').mkdir()
    (repo / 'runs' / 'ignored.txt').write_text('x')
    data = snapshot.overlay(repo)
    assert data is not None
    dest = tmp_path / 'checkout'
    snapshot.from_bundle(dest, snapshot.bundle(repo), snapshot.commit(repo), data)
    assert (dest / 'sim' / 'a.py').read_text() == 'a = 2\n'
    assert (dest / 'sim' / 'new' / 'b.py').read_text() == 'b = 1\n'
    assert not (dest / 'sim' / 'gone.py').exists() and not (dest / 'runs').exists()
    git(repo, 'checkout', '-q', '--', 'sim')
    shutil.rmtree(repo / 'sim' / 'new')
    assert snapshot.overlay(repo) is None


def test_public_code_is_only_what_main_or_next_holds(repo, tmp_path):
    mirror_parent = tmp_path / 'home'
    mirror_parent.mkdir()
    head = snapshot.commit(repo)
    snapshot.from_public(tmp_path / 'ok', mirror_parent / 'mirror.git', str(repo), head)
    assert (tmp_path / 'ok' / 'sim' / 'a.py').exists()
    git(repo, 'switch', '-q', '-c', 'private')
    (repo / 'sim' / 'a.py').write_text('a = 3\n')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-am', 'private')
    with pytest.raises(PermissionError):
        snapshot.from_public(tmp_path / 'no', mirror_parent / 'mirror.git', str(repo), snapshot.commit(repo))


def test_a_batch_file_becomes_specs_with_every_input_named_by_hash(repo, tmp_path):
    (tmp_path / 'brain.pt').write_bytes(b'parent weights')
    batch = tmp_path / 'grid.toml'
    batch.write_text(f'world = "{repo}/sim/world.toml"\ntrain = "{repo}/sim/train.toml"\n'
                     'on = "rented"\n'
                     '[[job]]\nname = "first"\nparent = "brain.pt"\n'
                     '[[job]]\nname = "second"\nparent = "job:first"\nseed = 2\non = "trusted"\n')
    made, blobs = jobs.specs(batch, tmp_path / 'runs', repo)
    for s in made:
        jobs.check(s)
    first, second = made
    assert not first['trusted'] and first['code']['overlay'] is None and first['samples'] == 64
    assert blobs[first['parent']['blob']] == b'parent weights' and second['parent'] == {'job': first['id']}
    assert blobs[first['world']] == b'size = 8\n' and second['seed'] == 2
    assert first['on'] == 'rented' and second['on'] == 'trusted'
    (repo / 'sim' / 'a.py').write_text('a = 9\n')
    dirty, _ = jobs.specs(batch, tmp_path / 'runs', repo)
    assert dirty[0]['trusted'] and dirty[0]['code']['overlay']
    batch.write_text('world = "w"\ntrain = "t"\nlr = 3\n[[job]]\nname = "x"\n')
    with pytest.raises(jobs.BadJob, match='unknown key'):
        jobs.load_batch(batch)
    batch.write_text('world = "w"\ntrain = "t"\non = "mac"\n[[job]]\nname = "x"\n')
    with pytest.raises(jobs.BadJob, match='on is one of'):
        jobs.load_batch(batch)


@pytest.fixture
def server(tmp_path):
    root = tmp_path / 'coord'
    httpd = coordinator.serve(root, port=0, signers=None)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{httpd.server_address[1]}'
    tokens = coordinator.Tokens(root)
    clients = {role: jobs.Client(url, tokens.add(role, role)) for role in coordinator.ROLES}
    yield httpd, clients
    httpd.shutdown()


def upload(client, s, sig='sig'):
    for data in (b'w', b't'):
        client.json('PUT', f'/api/blobs/{sha256(data)}', data)
    client.json('POST', '/api/jobs', {'spec': s, 'sig': sig})


def test_tokens_decide_who_may_do_what(server):
    httpd, c = server
    assert jobs.Client(c['admin'].server, 'nope').call('GET', '/api/jobs')[0] == 401
    assert c['donor'].call('GET', '/api/jobs')[0] == 404
    assert c['donor'].call('PUT', f'/api/blobs/{sha256(b"x")}', b'x')[0] == 404
    assert c['admin'].call('PUT', f'/api/blobs/{sha256(b"y")}', b'x')[0] == 400
    assert c['admin'].call('GET', '/api/health')[0] == 200


def test_a_donor_gets_public_jobs_and_only_their_blobs(server, tmp_path, monkeypatch):
    httpd, c = server
    monkeypatch.setattr(jobs, 'verify', lambda *a: True)
    c['admin'].json('PUT', f'/api/blobs/{sha256(b"private code")}', b'private code')
    upload(c['admin'], spec('a' * 12, trusted=True, overlay=sha256(b'private code'), added=1))
    upload(c['admin'], spec('b' * 12, added=2))
    assert c['donor'].call('GET', f'/api/blobs/{sha256(b"w")}')[0] == 403
    job = c['donor'].json('POST', '/api/claim', {})
    assert job['spec']['id'] == 'b' * 12
    assert c['donor'].call('POST', '/api/claim', {})[0] == 204
    assert c['donor'].call('GET', f'/api/blobs/{sha256(b"w")}') == (200, b'w')
    assert c['donor'].call('GET', f'/api/blobs/{sha256(b"private code")}')[0] == 403
    upload(c['admin'], spec('c' * 12, trusted=True, overlay=sha256(b'private code'), added=3, on='rented'))
    assert c['trusted'].json('POST', '/api/claim', {})['spec']['id'] == 'a' * 12
    assert c['trusted'].call('POST', '/api/claim', {})[0] == 204
    assert c['rented'].json('POST', '/api/claim', {})['spec']['id'] == 'c' * 12
    c['donor'].json('POST', f'/api/jobs/{"b" * 12}/beat', {'progress': {'samples': 32}})
    c['donor'].json('PUT', f'/api/jobs/{"b" * 12}/result', result(f'20261024-120000-nbbb-{"b" * 12}'))
    runs = tmp_path / 'runs'
    [path] = jobs.sync(c['admin'], runs)
    assert (path / 'evals.json').exists() and jobs.sync(c['admin'], runs) == []


def test_oversized_uploads_are_refused_before_they_are_read(server, monkeypatch):
    _, c = server
    monkeypatch.setitem(coordinator.LIMITS, 'blob', 10)
    big = b'x' * 11
    assert c['admin'].call('PUT', f'/api/blobs/{sha256(big)}', big)[0] == 413


def test_sync_refuses_a_result_that_reaches_outside_its_folder(tmp_path):
    s = spec()
    for bad in [result(f'20261024-120000-other-{"a" * 12}x'), result('..')]:
        with pytest.raises(jobs.BadJob):
            jobs.unpack(bad, s, tmp_path / 'runs')


FAKE_TRAIN = '''
import json, sys, pathlib
name = sys.argv[1]
run = pathlib.Path('..') / 'runs' / f'20261024-120000-{name}'
(run / 'checkpoints').mkdir(parents=True)
(run / 'metrics.jsonl').write_text(json.dumps({'samples': 64, 'samples_per_second': 10}) + '\\n')
(run / 'checkpoints' / '00000000064.pt').write_bytes(open(sys.argv[2], 'rb').read())
(run / 'run.json').write_text(json.dumps({'checkpoint': '00000000064.pt', 'machine': {}, 'world': sys.argv[2]}))
(run / 'evals.json').write_text('{}')
'''


@needs_ssh
def test_a_trusted_worker_runs_a_signed_job_on_uncommitted_code(server, repo, key, tmp_path, monkeypatch):
    _, c = server
    k, signers = key
    (repo / 'sim' / 'a.py').write_text('a = 2\n')
    batch = tmp_path / 'grid.toml'
    batch.write_text(f'world = "{repo}/sim/world.toml"\ntrain = "{repo}/sim/train.toml"\n[[job]]\nname = "one"\n')
    [s] = jobs.add(c['admin'], batch, k, tmp_path / 'runs', repo)
    monkeypatch.setattr(worker, 'sync', lambda sim: None)

    def command(spec, inputs):
        return [sys.executable, '-c', FAKE_TRAIN, jobs.run_name(spec), str(inputs['world'])]

    w = worker.Worker(c['trusted'], tmp_path / 'home', trusted=True, signers=signers, instance=57436340,
                      command=command)
    # what a stopped attempt leaves behind in the checkout
    stale = w.code(s) / 'runs' / f'20261024-110000-{jobs.run_name(s)}'
    stale.mkdir(parents=True)
    assert w.wants_work()
    w.start(c['trusted'].json('POST', '/api/claim', w.info()))
    for t in list(w.tasks.values()):
        while t.state not in ('done', 'failed'):
            threading.Event().wait(0.05)
    assert [p.read_text() for p in (tmp_path / 'home' / 'code').glob('*/sim/a.py')] == ['a = 2\n']
    [path] = jobs.sync(c['admin'], tmp_path / 'runs')
    assert json.loads((path / 'run.json').read_text())['machine']['instance'] == 57436340
    assert json.loads((path / 'job.json').read_text())['spec'] == s
    assert str(tmp_path) not in (path / 'run.json').read_text()
    assert (path / 'overlay.tar.gz').read_bytes() == snapshot.overlay(repo)
    assert path.name.endswith(jobs.run_name(s)) and not stale.exists()


@needs_ssh
def test_workers_refuse_unsigned_jobs_and_donors_refuse_trusted_ones(server, key, tmp_path):
    _, c = server
    k, signers = key
    w = worker.Worker(c['donor'], tmp_path / 'home', signers=signers)
    forged = worker.Task({'spec': spec(), 'sig': jobs.sign(spec() | {'seed': 5}, k)})
    with pytest.raises(worker.Refused, match='signature'):
        w.prepare(forged, tmp_path / 'job')
    trusted = worker.Task({'spec': spec(trusted=True), 'sig': jobs.sign(spec(trusted=True), k)})
    with pytest.raises(worker.Refused, match='trusted'):
        w.prepare(trusted, tmp_path / 'job')
