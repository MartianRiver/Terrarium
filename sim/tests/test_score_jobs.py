import io
import json
import sys
import tarfile
import threading

import pytest
from test_jobs import (CPU, LAPTOP_GPU, key, loose_configs, needs_ssh, own_repos_only, repo,  # noqa: F401
                       result, server, spec, store)

from terrarium import evals, jobs, worker
from terrarium.store import sha256

BRAIN = {'blob': sha256(b'brain'), 'file': 'brain.pt'}


def score(id: str, parent=None, added: float = 1.0, on: str | None = None) -> dict:
    s = spec(id, trusted=True, parent=parent or BRAIN, added=added, on=on)
    del s['train'], s['train_file']
    return s | {'kind': 'score', 'samples': 0, 'score': {'game': 'tree', 'episodes': 8, 'baselines': ['random']}}


def scores(name: str = '20261105-120000-sc') -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        data = b'{}'
        info = tarfile.TarInfo(f'{name}/games.json')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_each_machine_takes_the_kind_of_job_it_is_best_at_first(tmp_path):
    s = store(tmp_path)
    s.put(b'brain')
    s.add(score('a' * 12, added=1), 'sig')
    s.add(spec('b' * 12, added=2), 'sig')
    s.add(spec('c' * 12, added=3), 'sig')
    # the GPU laptop passes over the older score job for training, the CPU box takes it
    assert s.claim('Jellybean', True, specs=LAPTOP_GPU, version=10)['spec']['id'] == 'b' * 12
    assert s.claim('Kelpie', True, specs=CPU, version=10)['spec']['id'] == 'a' * 12
    # and with no score job left it trains rather than sit idle
    assert s.claim('Kelpie2', True, specs=CPU, version=10)['spec']['id'] == 'c' * 12


def test_score_jobs_skip_old_workers_and_pods_unless_kept_to_pods(tmp_path):
    s = store(tmp_path)
    s.put(b'brain')
    s.add(score('a' * 12), 'sig')
    assert s.claim('Kelpie', True, specs=CPU, version=9) is None
    assert s.claim('donor-1', False, role='donor', specs=CPU, version=10) is None
    assert s.claim('pod-1', True, role='rented', specs=LAPTOP_GPU, version=10) is None
    s.add(score('b' * 12, added=2, on='rented'), 'sig')
    assert s.claim('pod-1', True, role='rented', specs=LAPTOP_GPU, version=10)['spec']['id'] == 'b' * 12


def test_a_score_job_waits_for_the_training_it_scores_and_finishes_without_a_brain(tmp_path):
    s = store(tmp_path)
    s.add(spec('a' * 12, added=1), 'sig')
    s.add(score('b' * 12, parent={'job': 'a' * 12}, added=2), 'sig')
    assert s.claim('Kelpie', True, specs=CPU, version=10)['spec']['id'] == 'a' * 12
    assert s.claim('Kelpie2', True, specs=CPU, version=10) is None
    s.finish('a' * 12, 'Kelpie', result())
    job = s.claim('Kelpie', True, specs=CPU, version=10)
    assert job['spec']['id'] == 'b' * 12 and s.parent_blob(job) == s.read('a' * 12)['final']
    s.finish('b' * 12, 'Kelpie', scores())
    done = s.read('b' * 12)
    assert done['state'] == 'done' and done['final'] is None and done['result']


def test_a_batch_can_score_its_own_training_job(repo, tmp_path):
    batch = tmp_path / 'grid.toml'
    head = f'world = "{repo}/sim/world.toml"\ntrain = "{repo}/sim/train.toml"\n[[job]]\nname = "t"\n'
    batch.write_text(head + '[[job]]\nname = "t-score"\nbrain = "job:t"\n'
                     'score = { game = "tree", episodes = 16, held_out = true, wiped_every = 3.0, baselines = ["picker"] }\n')
    made, _ = jobs.specs(batch, tmp_path / 'runs', repo)
    for s in made:
        jobs.check(s)
    train, sc = made
    assert sc['kind'] == 'score' and sc['parent'] == {'job': train['id']} and 'train' not in sc
    assert sc['samples'] == 0 and sc['seed'] == evals.HELD_OUT and sc['trusted'] and not train['trusted']
    assert sc['score'] == {'game': 'tree', 'episodes': 16, 'wiped_every': 3.0, 'baselines': ['picker']}
    for s in made:
        assert 'line' not in s and 'question' not in s
    batch.write_text(head.replace('[[job]]', 'line = "nights"\nquestion = "Does it keep the tree?"\n[[job]]', 1)
                     + '[[job]]\nname = "t-score"\nbrain = "job:t"\nscore = { game = "tree" }\n')
    made, _ = jobs.specs(batch, tmp_path / 'runs', repo)
    for s in made:
        jobs.check(s)
        assert s['line'] == 'nights' and s['question'] == 'Does it keep the tree?'
    for bad, why in [('score = { game = "golf" }\nbrain = "job:t"', 'no game'),
                     ('score = { game = "tree", baselines = ["nobody"] }\nbrain = "job:t"', 'no baseline'),
                     ('score = { game = "tree", wiped_on_event = true }\nbrain = "job:t"', 'no event'),
                     ('score = { game = "tree" }', 'a brain'),
                     ('score = { game = "tree", episodes = 0 }\nbrain = "job:t"', 'episodes')]:
        batch.write_text(head + f'[[job]]\nname = "s"\n{bad}\n')
        with pytest.raises(jobs.BadJob, match=why):
            jobs.specs(batch, tmp_path / 'runs', repo)
    batch.write_text(head + '[[job]]\nname = "s"\nbrain = "job:t"\nscore = { game = "tree" }\n'
                     '[[job]]\nname = "u"\nparent = "job:s"\n')
    with pytest.raises(jobs.BadJob, match='makes no brain'):
        jobs.specs(batch, tmp_path / 'runs', repo)
    with pytest.raises(jobs.BadJob, match='no train'):
        jobs.check(sc | {'train': train['train']})
    with pytest.raises(jobs.BadJob, match='only for trusted'):
        jobs.check(sc | {'trusted': False})


FAKE_SCORE = '''
import json, sys
open(sys.argv[1], 'w').write(json.dumps({'game': 'tree', 'players': {}}))
print('the table')
'''


@needs_ssh
def test_a_worker_scores_a_signed_brain_and_it_syncs_into_scores(server, repo, key, tmp_path, monkeypatch):
    _, c = server
    k, signers = key
    (tmp_path / 'brain.pt').write_bytes(b'weights')
    batch = tmp_path / 'check.toml'
    batch.write_text(f'world = "{repo}/sim/world.toml"\n[[job]]\nname = "sc"\nbrain = "brain.pt"\n'
                     'score = { game = "tree", episodes = 4 }\n')
    [s] = jobs.add(c['admin'], batch, k, tmp_path / 'runs', repo)
    monkeypatch.setattr(worker, 'sync', lambda sim: None)
    monkeypatch.setattr(worker, 'check_lock', lambda lock: None)
    seen = {}

    def scorer(spec, inputs, sim, out):
        seen['brain'] = (sim / inputs['parent']).read_bytes()
        return [sys.executable, '-c', FAKE_SCORE, str(out)]

    w = worker.Worker(c['trusted'], tmp_path / 'home', trusted=True, signers=signers, scorer=scorer)
    w.start(c['trusted'].json('POST', '/api/claim', w.info()))
    for t in list(w.tasks.values()):
        while t.state not in ('done', 'failed'):
            threading.Event().wait(0.05)
    assert seen['brain'] == b'weights'
    [path] = jobs.sync(c['admin'], tmp_path / 'runs')
    assert path.parent == tmp_path / 'runs' / 'scores' and path.name.endswith(jobs.run_name(s))
    assert (path / 'report.txt').read_text().strip() == 'the table'
    record = json.loads((path / 'score.json').read_text())
    assert record['game'] == 'tree' and record['seed'] == evals.SEED and record['machine']['cores']
    assert json.loads((path / 'job.json').read_text())['spec'] == s
    assert jobs.sync(c['admin'], tmp_path / 'runs') == []


def test_the_score_command_plays_the_games_the_spec_names(tmp_path):
    w = worker.Worker(None, tmp_path / 'home', trusted=True)  # type: ignore[arg-type]
    s = score('a' * 12) | {'seed': 2001000}
    s['score'] |= {'wiped_every': 3.0, 'baselines': ['picker', 'random']}
    cmd = w.score_command(s, {'world': tmp_path / 'w.toml', 'parent': tmp_path / 'b.pt'}, tmp_path, tmp_path / 'g.json')
    i = cmd.index('terrarium.games')
    assert cmd[i + 1] == 'tree' and cmd[cmd.index('--seed') + 1] == '2001000'
    assert cmd[cmd.index('--baseline') + 1:cmd.index('--brain')] == ['picker', 'random']
    assert cmd[cmd.index('--wiped-every') + 1] == '3.0' and '--wiped' not in cmd


def test_a_score_job_can_wipe_on_the_games_event_and_only_new_workers_get_it(tmp_path):
    assert jobs.bad_score({'game': 'tree-home', 'wiped_on_event': True}) is None
    assert 'wrong type' in jobs.bad_score({'game': 'tree-home', 'wiped_on_event': 1})
    w = worker.Worker(None, tmp_path / 'home', trusted=True)  # type: ignore[arg-type]
    s = score('a' * 12)
    s['score'] |= {'game': 'tree-home', 'wiped_on_event': True}
    cmd = w.score_command(s, {'world': tmp_path / 'w.toml', 'parent': tmp_path / 'b.pt'}, tmp_path, tmp_path / 'g.json')
    assert '--wiped-on-event' in cmd and '--wiped' not in cmd
    plain = w.score_command(score('b' * 12), {'world': tmp_path / 'w.toml', 'parent': tmp_path / 'b.pt'}, tmp_path,
                            tmp_path / 'g.json')
    assert '--wiped-on-event' not in plain
    st = store(tmp_path)
    st.put(b'brain')
    st.add(s, 'sig')
    assert st.claim('Kelpie', True, specs=CPU, version=12) is None
    assert st.claim('Kelpie', True, specs=CPU, version=worker.VERSION)['spec']['id'] == 'a' * 12
