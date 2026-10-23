import json
from datetime import datetime

import pytest

from terrarium.compute import lineage_hours, seconds, spent, totals


def make_run(root, name, started, finished=None, last=None, brain='', parent=None):
    run = root / name
    run.mkdir(parents=True)
    record = {'id': name, 'started': started, 'brain': brain, 'parent': parent and {'id': parent}}
    if finished:
        record['finished'] = finished
    (run / 'run.json').write_text(json.dumps(record))
    if last is not None:
        (run / 'metrics.jsonl').write_text(json.dumps({'seconds': last / 2}) + '\n' + json.dumps({'seconds': last}) + '\n')
    return record


def at(stamp):
    return datetime.fromisoformat(stamp)


def test_a_run_counts_start_to_finish_or_up_to_its_last_update(tmp_path):
    make_run(tmp_path, 'done', '2026-10-23T10:00:00+1100', '2026-10-23T10:30:00+1100', last=1700)
    make_run(tmp_path, 'stopped', '2026-10-23T10:00:00+1100', last=563.1)
    make_run(tmp_path, 'crashed', '2026-10-23T10:00:00+1100')
    live = make_run(tmp_path, 'live', '2026-10-23T10:00:00+1100', last=20.5)['id']
    with open(tmp_path / live / 'metrics.jsonl', 'a') as f:
        f.write('{"seconds": 2')
    assert seconds(tmp_path / 'done') == 1800
    assert seconds(tmp_path / 'stopped') == 563.1
    assert seconds(tmp_path / 'live') == 20.5
    assert seconds(tmp_path / 'crashed') == 0


def test_spent_takes_runs_and_rentals_in_the_window(tmp_path):
    runs = tmp_path / 'runs'
    make_run(runs, 'before', '2026-10-23T09:00:00+1100', '2026-10-23T10:00:00+1100')
    make_run(runs, 'mac', '2026-10-23T13:00:00+1100', '2026-10-23T13:36:00+1100')
    # a pod's clock is UTC: 02:30 there is 13:30 here
    make_run(runs, 'pod', '2026-10-23T02:30:00+0000', '2026-10-23T02:48:00+0000')
    sessions = tmp_path / 'compute.toml'
    sessions.write_text('[[session]]\ninstance = 1\nended = "2026-10-23T12:00:00+11:00"\ndollars = 5.0\n'
                        '[[session]]\ninstance = 2\nended = "2026-10-23T14:00:00+11:00"\ndollars = 0.271\n')
    since, until = at('2026-10-23T12:30:00+11:00'), at('2026-10-23T15:00:00+11:00')
    assert spent(runs, since, until, sessions) == {'runs': 2, 'hours': 0.9, 'dollars': 0.27}


def test_lineage_follows_parents_through_runs_then_the_lineage_file(tmp_path):
    make_run(tmp_path, 'first', '2026-10-23T10:00:00+1100', '2026-10-23T11:00:00+1100', brain='aaa')
    middle = make_run(tmp_path, 'middle', '2026-10-24T10:00:00+1100', '2026-10-24T10:30:00+1100', brain='bbb',
                      parent='aaa')
    last = make_run(tmp_path, 'last', '2026-10-25T10:00:00+1100', '2026-10-25T10:15:00+1100', parent='bbb')
    assert lineage_hours(tmp_path, middle, []) == 1.5
    assert lineage_hours(tmp_path, last, []) == 1.75
    # the parent's runs are on another machine; its entry in brains.toml still says what it took
    elsewhere = make_run(tmp_path, 'elsewhere', '2026-10-25T10:00:00+1100', '2026-10-25T10:06:00+1100', parent='ccc')
    assert lineage_hours(tmp_path, elsewhere, [{'id': 'ccc', 'compute': {'lineage_hours': 2.0}}]) == 2.1
    with pytest.raises(LookupError, match='ccc'):
        lineage_hours(tmp_path, elsewhere, [])


def test_totals_carry_on_from_the_last_brain(tmp_path):
    old = make_run(tmp_path, 'old', '2026-10-23T10:00:00+1100', '2026-10-23T11:00:00+1100')
    new = make_run(tmp_path, 'new', '2026-10-24T10:00:00+1100', '2026-10-24T10:30:00+1100')
    first = totals(tmp_path, old, [], at('2026-10-23T12:00:00+11:00'), tmp_path / 'none.toml')
    assert first == {'until': '2026-10-23T12:00:00+11:00', 'lineage_hours': 1.0, 'runs': 1, 'hours': 1.0,
                     'dollars': 0.0, 'total_hours': 1.0, 'total_dollars': 0.0}
    second = totals(tmp_path, new, [{'id': 'x', 'compute': first}], at('2026-10-24T12:00:00+11:00'),
                    tmp_path / 'none.toml')
    assert (second['runs'], second['hours'], second['total_hours']) == (1, 0.5, 1.5)
