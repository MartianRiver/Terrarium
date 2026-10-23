import json
import tomllib

import pytest

from terrarium import evals, runs
from terrarium.brain import SHAPE, Brain, brain_id, save
from terrarium.promote import LINEAGE, Refused, lineage, promote


def score(food, food_err, alive, alive_err):
    return {'episodes': 64, 'seed': evals.SEED, 'food_per_minute': {'mean': food, 'stderr': food_err},
            'seconds_alive': {'mean': alive, 'stderr': alive_err}}


GOOD = score(9.8, 0.5, 153.0, 4.0)
RANDOM = score(0.26, 0.07, 49.6, 2.1)


def fake_run(tmp_path, scores=GOOD, **record):
    """A finished run folder as train.py leaves it, from this checkout's HEAD."""
    run = tmp_path / 'runs' / '20261023-120000-solo'
    (run / 'checkpoints').mkdir(parents=True)
    checkpoint = run / 'checkpoints' / '00000032768.pt'
    save(Brain(**SHAPE), checkpoint)
    (run / 'evals.json').write_text(json.dumps({'checkpoint': checkpoint.name, 'random': RANDOM, 'brain': scores}))
    (run / 'run.json').write_text(json.dumps({
        'id': run.name, 'commit': runs.git('rev-parse', 'HEAD'), 'dirty': False, 'scratch': False,
        'world': {'file': 'solo.toml'}, 'parent': None, 'schema': {'version': 1},
        'started': '2026-10-23T12:00:00+1100', 'finished': '2026-10-23T12:30:00+1100', 'samples': 32768, 'checkpoint': checkpoint.name, 'brain': brain_id(checkpoint),
        **record}))
    return run


def test_promote_writes_lineage_and_backup(tmp_path):
    run, path = fake_run(tmp_path), tmp_path / 'brains.toml'
    entry = promote(run, '0.2', tmp_path / 'backups', path, branch='HEAD', like='a worm',
                    sessions=tmp_path / 'compute.toml')
    copy = tmp_path / 'backups' / 'brains' / entry['file']
    assert brain_id(copy) == entry['id'] == json.loads((run / 'run.json').read_text())['brain']
    [saved] = lineage(path)
    assert saved == entry
    assert saved['parent'] == '' and saved['release'] == 'v0.2.0'
    assert saved['evals']['brain']['food_per_minute'] == 9.8
    assert saved['like'] == 'a worm'
    assert (saved['compute']['runs'], saved['compute']['hours'], saved['compute']['total_hours']) == (1, 0.5, 0.5)
    with pytest.raises(Refused, match='already has a brain'):
        promote(run, '0.2', tmp_path / 'backups', path, branch='HEAD')


@pytest.mark.parametrize('record, why', [
    ({'scratch': True, 'dirty': True}, 'scratch'),
    ({'dirty': True}, 'scratch'),
    ({'commit': '0' * 40}, "isn't on"),
    ({'brain': '0' * 64}, 'has changed'),
])
def test_promote_refuses_untraceable_runs(tmp_path, record, why):
    with pytest.raises(Refused, match=why):
        promote(fake_run(tmp_path, **record), '0.2', tmp_path / 'backups', tmp_path / 'brains.toml', branch='HEAD')
    assert not (tmp_path / 'backups').exists()


def test_promote_refuses_unfinished_runs(tmp_path):
    run = fake_run(tmp_path)
    record = json.loads((run / 'run.json').read_text())
    del record['finished']
    (run / 'run.json').write_text(json.dumps(record))
    with pytest.raises(Refused, match='never finished'):
        promote(run, '0.2', tmp_path / 'backups', tmp_path / 'brains.toml', branch='HEAD')


def test_promote_refuses_brains_that_dont_clearly_beat_random(tmp_path):
    with pytest.raises(Refused, match='under twice'):
        promote(fake_run(tmp_path, scores=score(0.5, 0.01, 153.0, 4.0)), '0.2', tmp_path / 'b', tmp_path / 'l.toml',
                branch='HEAD')


def test_beats():
    assert evals.beats(GOOD, RANDOM) == []
    # twice random's food but within the noise
    assert evals.beats(score(0.6, 0.2, 60.0, 2.0), RANDOM) == [
        'food_per_minute is ahead by 0.34, not more than three standard errors (0.64)']
    # plenty of food, but no longer alive than random
    assert 'seconds_alive' in evals.beats(score(5.0, 0.5, 52.0, 3.0), RANDOM)[0]


def test_the_lineage_file_reads():
    assert isinstance(tomllib.loads(LINEAGE.read_text()).get('brain', []), list)
