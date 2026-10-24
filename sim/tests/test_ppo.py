import json

import numpy as np
import pytest
import torch

from terrarium import runs
from terrarium.brain import SHAPE, Brain
from terrarium.brain import load as load_brain
from terrarium.config import DEFAULT, TRAIN
from terrarium.ppo import Episodes, advantages
from terrarium.train import cpu_quota, train


def test_advantages_by_hand():
    rewards = np.array([[1.0], [0.0], [2.0]])
    values = np.array([[0.5], [0.4], [0.3]])
    dones = np.array([[0.0], [1.0], [0.0]])
    adv, ret = advantages(rewards, values, dones, np.array([0.2]), gamma=0.9, lam=0.8)
    # the episode ends on step 1, so step 0 bootstraps from step 1's value and step 1 from nothing
    assert adv[:, 0] == pytest.approx([0.86 + 0.9 * 0.8 * -0.4, -0.4, 2 + 0.9 * 0.2 - 0.3])
    assert ret == pytest.approx(adv + values)


def test_episodes_add_up_and_reset():
    e = Episodes(2, dt=0.5)
    both = np.array([True, True])
    e.add(np.array([1.0, 0.0]), np.array([False, False]), both)
    e.add(np.array([1.0, 2.0]), np.array([True, False]), both)
    assert e.take() == {'episodes': 1, 'episode_return': 2.0, 'episode_seconds': 1.0}
    assert e.take() == {'episodes': 0}
    e.add(np.array([0.0, 1.0]), np.array([False, True]), both)
    assert e.take()['episode_return'] == 3.0


def test_the_dead_add_nothing_until_their_arena_starts_over():
    e = Episodes(2, dt=0.5)
    e.add(np.array([1.0, 1.0]), np.array([True, False]), np.array([True, True]))
    # the first died; its arena ending later isn't a second episode
    e.add(np.array([5.0, 1.0]), np.array([True, True]), np.array([False, True]))
    assert e.take() == {'episodes': 2, 'episode_return': 1.5, 'episode_seconds': 0.75}


def test_dirty_tree_needs_scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, 'dirty', lambda: True)
    with pytest.raises(runs.DirtyTree, match='--scratch'):
        runs.Run('x', {}, root=tmp_path)
    run = runs.Run('x', {'seed': 3}, scratch=True, root=tmp_path)
    record = json.loads((run.dir / 'run.json').read_text())
    assert record['scratch'] and record['dirty'] and record['seed'] == 3
    assert (run.dir / 'diff.patch').exists() and set(record['versions']) == {'python', 'numpy', 'pymunk', 'torch'}


def short(tmp_path):
    """A world with 3 s episodes and a few hundred samples of training on the CPU, so a whole run takes seconds."""
    world = tmp_path / 'world.toml'
    world.write_text((DEFAULT.parent / 'solo.toml').read_text().replace('seconds = 180.0', 'seconds = 3.0'))
    text = TRAIN.read_text()
    for key, value in (('samples', 256), ('arenas', 4), ('steps', 16), ('minibatches', 2), ('checkpoint_every', 2)):
        text = '\n'.join(f'{key} = {value}' if line.startswith(f'{key} =') else line for line in text.splitlines())
    trainer = tmp_path / 'train.toml'
    trainer.write_text(text + '\n')
    return world, trainer


def test_a_short_run_leaves_a_full_record(tmp_path):
    world, trainer = short(tmp_path)
    run = train('smoke', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu')
    record = json.loads((run.dir / 'run.json').read_text())
    assert record['train']['config']['ppo']['samples'] == 256 and record['world']['file'] == 'world.toml'
    assert record['samples'] == 256 and record['parent'] is None and 'finished' in record and record['id'] == run.id
    rows = [json.loads(line) for line in (run.dir / 'metrics.jsonl').read_text().splitlines()]
    assert [r['update'] for r in rows] == [1, 2, 3, 4] and all(np.isfinite(r['policy_loss']) for r in rows)
    assert sorted(p.name for p in (run.dir / 'checkpoints').iterdir()) == ['00000000128.pt', '00000000256.pt']
    evals = json.loads((run.dir / 'evals.json').read_text())
    assert set(evals) == {'checkpoint', 'random', 'brain'}

    # and a second run carries on from it, recording where it came from
    child = train('child', world, trainer, parent=run.dir / 'checkpoints' / '00000000256.pt', scratch=True,
                  root=tmp_path / 'runs', device='cpu')
    child_record = json.loads((child.dir / 'run.json').read_text())
    assert child_record['parent']['id'] == record['brain'] and child_record['id'] == child.id
    _, meta = load_brain(child.dir / 'checkpoints' / '00000000256.pt')
    assert meta['parent'] == record['brain'] and meta['run'] == child.id and meta['scratch']


def test_training_changes_the_brain(tmp_path):
    world, trainer = short(tmp_path)
    torch.manual_seed(0)
    run = train('moves', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu')
    trained, _ = load_brain(run.dir / 'checkpoints' / '00000000256.pt')
    torch.manual_seed(0)
    fresh = Brain(**SHAPE)
    assert not torch.equal(trained.policy.weight, fresh.policy.weight)


def test_workers_split_the_arenas(tmp_path):
    world, trainer = short(tmp_path)
    run = train('split', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu', workers=3)
    record = json.loads((run.dir / 'run.json').read_text())
    assert record['workers'] == 3 and record['device'] == 'cpu' and record['samples'] == 256
    rows = [json.loads(line) for line in (run.dir / 'metrics.jsonl').read_text().splitlines()]
    assert [r['update'] for r in rows] == [1, 2, 3, 4] and sum(r['episodes'] for r in rows) > 0
    with pytest.raises(ValueError, match='at least one arena'):
        train('too-many', world, trainer, scratch=True, root=tmp_path / 'runs', device='cpu', workers=5)
    assert len(list((tmp_path / 'runs').iterdir())) == 1


def test_cpu_quota_reads_cgroup(tmp_path):
    # a rented container showed 255 cores to torch but was allowed 30.6
    f = tmp_path / 'cpu.max'
    f.write_text('3060000 100000\n')
    assert cpu_quota(f) == 30
    f.write_text('max 100000\n')
    assert cpu_quota(f) is None
    assert cpu_quota(tmp_path / 'missing') is None
