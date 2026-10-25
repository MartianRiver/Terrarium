import json
from datetime import datetime

import pytest

from terrarium.compute import behind, everything, lineage_hours, rented_on, seconds, spent, totals


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
    sessions.write_text('[[session]]\ninstance = 1\nstarted = "2026-10-23T09:00:00+11:00"\n'
                        'ended = "2026-10-23T12:00:00+11:00"\ndollars = 5.0\n'
                        '[[session]]\ninstance = 2\nstarted = "2026-10-23T13:00:00+11:00"\n'
                        'ended = "2026-10-23T14:00:00+11:00"\ndollars = 0.271\n')
    since, until = at('2026-10-23T12:30:00+11:00'), at('2026-10-23T15:00:00+11:00')
    assert spent(runs, since, until, sessions) == {'runs': 2, 'hours': 0.9, 'rented_hours': 1.0, 'dollars': 0.27}


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
                     'rented_hours': 0.0, 'dollars': 0.0, 'total_hours': 1.0, 'total_dollars': 0.0}
    second = totals(tmp_path, new, [{'id': 'x', 'compute': first}], at('2026-10-24T12:00:00+11:00'),
                    tmp_path / 'none.toml')
    assert (second['runs'], second['hours'], second['total_hours']) == (1, 0.5, 1.5)


M3 = {'platform': 'macOS-26.6.2-arm64-arm-64bit-Mach-O', 'processor': 'arm', 'cpu': 'Apple M3', 'memory_gb': 16}
POD = {'platform': 'Linux-6.8.0-x86_64-with-glibc2.39', 'processor': 'x86_64'}


def make_trained(root, name, started, finished, machine, device, gpu=None, brain='', parent=None):
    run = root / name
    run.mkdir(parents=True)
    (run / 'run.json').write_text(json.dumps({'id': name, 'started': started, 'finished': finished, 'brain': brain,
                                              'parent': parent, 'machine': machine, 'device': device, 'gpu': gpu}))
    rows = [{'samples': 100, 'seconds': 1800}, {'samples': 200, 'seconds': 3600}]
    (run / 'metrics.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


def test_what_went_into_a_brain_per_machine(tmp_path):
    runs = tmp_path / 'runs'
    make_trained(runs, 'mac', '2026-10-24T09:00:00+1100', '2026-10-24T10:00:00+1100', M3, 'mps', brain='aaa')
    # aaa2 is aaa with new actions set up, no training; the pod's clock is UTC
    made = {'id': 'aaa2', 'meta': {'parent': 'aaa'}}
    make_trained(runs, 'pod1', '2026-10-23T23:30:00+0000', '2026-10-24T00:30:00+0000', POD, 'cuda', 'NVIDIA A10',
                 brain='bbb', parent=made)
    make_trained(runs, 'pod2', '2026-10-23T23:30:00+0000', '2026-10-24T00:30:00+0000', POD, 'cuda', 'NVIDIA A10')
    # carries on from pod1's checkpoint halfway through
    make_trained(runs, 'last', '2026-10-24T13:00:00+1100', '2026-10-24T13:15:00+1100', M3, 'mps',
                 parent={'id': 'ccc', 'meta': {'run': 'pod1', 'samples': 100}})
    sessions = tmp_path / 'compute.toml'
    sessions.write_text('[[machine]]\ncpu = "Apple M3"\nmemory_gb = 16\nname = "MacBook Air 15-inch, M3, 16 GB"\n'
                        '[[session]]\ngpu = "A10"\ncpu = "Xeon Gold 6342, 24 cores"\nstarted = "2026-10-24T10:00:00+11:00"\n'
                        'ended = "2026-10-24T12:30:00+11:00"\ndollars = 1.0\n'
                        '[[session]]\ngpu = "RTX 3060 Ti"\nstarted = "2026-10-24T10:00:00+11:00"\n'
                        'ended = "2026-10-24T10:10:00+11:00"\ndollars = 0.01\n')
    got = behind(runs, runs / 'last', sessions)
    assert [(r['id'], r['hours'], r['rented_hours'], round(r['dollars'], 3)) for r in got['runs']] == [
        ('last', 0.25, 0, 0), ('pod1', 0.5, 0.625, 0.25), ('mac', 1.0, 0, 0)]
    assert [(h['hardware'], h['runs'], h['hours'], round(h['dollars'], 3)) for h in got['hardware']] == [
        ('MacBook Air 15-inch, M3, 16 GB', 2, 1.25, 0), ('A10, Xeon Gold 6342, 24 cores', 1, 0.5, 0.25)]
    assert got['missing'] is None
    everyone = everything(runs, sessions)
    assert [(h['hardware'], h['runs'], h['hours']) for h in everyone['hardware']] == [
        ('A10, Xeon Gold 6342, 24 cores', 2, 2.0), ('MacBook Air 15-inch, M3, 16 GB', 2, 1.25)]
    assert everyone['hardware'][0]['rented_hours'] == 2.5
    assert everyone['unused']['rentals'] == 1 and round(everyone['unused']['rented_hours'], 3) == 0.167
    assert everyone['dollars'] == 1.01 and round(everyone['rented_hours'], 3) == 2.667


def test_a_run_that_names_its_instance_is_matched_by_it():
    pod = {'started': '2026-10-24T10:30:00+1100', 'device': 'cuda', 'gpu': 'NVIDIA A10', 'machine': POD | {'instance': 2}}
    window = {'started': '2026-10-24T10:00:00+11:00', 'ended': '2026-10-24T11:00:00+11:00', 'gpu': 'A10'}
    assert [rented_on(pod, window | {'instance': i}) for i in (1, 2)] == [False, True]


def test_a_pod_whose_cpu_differs_is_another_rental():
    pod = {'started': '2026-10-24T10:30:00+1100', 'device': 'cuda', 'gpu': 'NVIDIA GeForce RTX 3060',
           'machine': POD | {'cpu': 'Intel(R) Xeon(R) Gold 6154 CPU @ 3.00GHz'}}
    window = {'started': '2026-10-24T10:00:00+11:00', 'ended': '2026-10-24T11:00:00+11:00', 'gpu': 'RTX 3060'}
    assert [rented_on(pod, window | {'cpu': c}) for c in ('Xeon Gold 6154, 16 cores', 'Xeon E5-2682 v4, 16 cores')] == [
        True, False]
    assert rented_on(pod, window)


def test_cpu_names_and_old_records():
    from terrarium.compute import cpu_name, hardware
    assert cpu_name('Intel(R) Xeon(R) Gold 6154 CPU @ 3.00GHz') == 'Xeon Gold 6154'
    assert cpu_name('AMD EPYC 7662 64-Core Processor') == 'EPYC 7662'
    assert cpu_name('AMD Ryzen 9 3950X 16-Core Processor') == 'Ryzen 9 3950X'
    pod = {'device': 'cuda', 'gpu': 'NVIDIA GeForce RTX 3060', 'machine': POD | {'cpu': 'AMD EPYC 7662 64-Core Processor'},
           'started': '2026-10-24T10:30:00+1100'}
    assert hardware(pod, []) == 'RTX 3060, EPYC 7662'
    mine = [{'cpu': 'Apple M3', 'memory_gb': 16, 'platform': 'macOS', 'name': 'the Air'}]
    assert hardware({'machine': {'platform': 'macOS-26.6.2-arm64-arm-64bit-Mach-O', 'processor': 'arm'}}, [], mine) == 'the Air'
    assert hardware({'machine': M3}, [], mine) == 'the Air'
