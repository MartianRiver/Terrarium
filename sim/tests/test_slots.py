import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from test_machine import QUIET, watch

from terrarium import calibrate, machine, worker
from terrarium.machine import Rules
from terrarium.store import scoring

SLEEP = [sys.executable, '-c', 'import time; time.sleep(60)']


def job(name: str, score: bool = False) -> dict:
    spec = {'id': name.ljust(12, '0'), 'name': name, 'batch': 'b', 'samples': 64}
    return {'spec': spec | ({'kind': 'score'} if score else {}), 'sig': ''}


class Queue:
    """A coordinator that hands jobs out in order and takes returned ones back to the front."""

    def __init__(self, *jobs):
        self.waiting, self.every, self.calls = list(jobs), {j['spec']['id']: j for j in jobs}, []

    def json(self, method, path, body=None):
        self.calls.append(path)
        if path == '/api/hello':
            return {'returned': []}
        if path == '/api/claim':
            return self.waiting.pop(0) if self.waiting else None
        if path.endswith('/return'):
            self.waiting.insert(0, self.every[path.split('/')[3]])

    def returned(self) -> list[str]:
        return [c.split('/')[3] for c in self.calls if c.endswith('/return')]


def until(cond, timeout: float = 10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError('timed out')


@pytest.fixture
def fake_work(monkeypatch):
    """Workers whose jobs are sleeping processes, held until the job is handed back or told to end."""
    procs = []
    done = {}

    def work(self, task):
        task.state = 'scoring' if scoring(task.spec) else 'training'
        task.proc = subprocess.Popen(SLEEP)
        procs.append(task.proc)
        done[task.id] = task.gone
        try:
            task.gone.wait(60)
        finally:
            machine.kill(task.proc.pid)
            with self.lock:
                self.tasks.pop(task.id, None)

    monkeypatch.setattr(worker.Worker, 'work', work)
    monkeypatch.setattr(worker, 'POLL', 0.02)
    monkeypatch.setattr(worker, 'BUSY', 0.02)
    yield done
    for p in procs:
        if p.poll() is None:
            p.kill()


def start(client, tmp_path, slots=2):
    w, fake = watch()
    wk = worker.Worker(client, tmp_path, slots=slots, rules=Rules(), watch=w)  # type: ignore[arg-type]
    threading.Thread(target=wk.loop, daemon=True).start()
    return wk, fake


def test_two_slots_run_two_jobs_at_once_and_each_job_records_what_ran_beside_it(fake_work, tmp_path):
    queue = Queue(job('a'), job('b'), job('c'))
    wk, _ = start(queue, tmp_path)
    try:
        until(lambda: len(wk.tasks) == 2 and all(t.state == 'training' for t in wk.tasks.values()))
        time.sleep(0.3)
        # the third waits for a free slot
        assert len(wk.tasks) == 2 and len(queue.waiting) == 1
        wk.mind()
        assert [t.beside for t in wk.tasks.values()] == [1, 1]
        record = next(iter(wk.tasks.values())).job_record()
        assert record['beside'] == 1 and record['spec']['batch'] == 'b' and 'sig' in record
        assert wk.info()['slots'] == 2
    finally:
        wk.stop()


def test_a_job_that_ran_alone_records_none_beside_it(running_one):
    wk, task = running_one
    wk.mind()
    assert task.beside == 0 and task.job_record()['beside'] == 0


@pytest.fixture
def running_one(tmp_path):
    w, _ = watch()
    wk = worker.Worker(Queue(), tmp_path, slots=2, rules=Rules(), watch=w)  # type: ignore[arg-type]
    task = worker.Task(job('a'))
    task.proc = subprocess.Popen(SLEEP)
    task.state = 'training'
    wk.tasks[task.id] = task
    yield wk, task
    task.proc.kill()


def test_a_score_job_waits_for_an_empty_machine_and_nothing_starts_beside_it(fake_work, tmp_path):
    queue = Queue(job('a'), job('s', score=True), job('b'))
    wk, _ = start(queue, tmp_path)
    try:
        until(lambda: queue.returned() == ['s' + '0' * 11])
        # handed back, not started, and nothing else claimed while the training job runs
        time.sleep(0.3)
        assert list(wk.tasks) == ['a' + '0' * 11] and wk.score_waits
        assert [j['spec']['name'] for j in queue.waiting] == ['s', 'b']
        fake_work['a' + '0' * 11].set()
        until(lambda: list(wk.tasks) == ['s' + '0' * 11])
        # the score job has the machine: the free slot stays free
        time.sleep(0.3)
        assert list(wk.tasks) == ['s' + '0' * 11] and [j['spec']['name'] for j in queue.waiting] == ['b']
        assert not wk.wants_work()
        fake_work['s' + '0' * 11].set()
        until(lambda: list(wk.tasks) == ['b' + '0' * 11])
    finally:
        wk.stop()


@pytest.fixture
def two(tmp_path):
    w, fake = watch()
    client = Queue(job('a'), job('b'))
    wk = worker.Worker(client, tmp_path, slots=2, rules=Rules(), watch=w)  # type: ignore[arg-type]
    procs = []
    for j in client.every.values():
        task = worker.Task(j)
        task.proc = subprocess.Popen(SLEEP)
        task.state = 'training'
        wk.tasks[task.id] = task
        procs.append(task.proc)
    yield wk, fake, client, procs
    for p in procs:
        if p.poll() is None:
            p.kill()


def test_pausing_suspends_every_running_job_and_resuming_carries_them_all_on(two):
    wk, fake, _, procs = two
    wk.paused = True
    wk.mind(now=1000)
    assert [t.state for t in wk.tasks.values()] == ['paused', 'paused']
    assert all(machine.tree(p.pid)[0].status() == 'stopped' for p in procs) or sys.platform == 'win32'
    wk.paused = False
    wk.mind(now=1030)
    assert [(t.state, t.paused) for t in wk.tasks.values()] == [('training', 30), ('training', 30)]
    fake.seen = QUIET._replace(idle=5)
    wk.mind(now=2000)
    assert [t.state for t in wk.tasks.values()] == ['paused', 'paused']


def test_a_game_hands_every_running_job_back(two):
    wk, fake, client, procs = two
    fake.seen = QUIET._replace(fullscreen=True)
    wk.mind(now=1000)
    assert sorted(client.returned()) == ['a' + '0' * 11, 'b' + '0' * 11]
    assert all(p.wait(timeout=10) is not None for p in procs)


def test_stopping_the_worker_hands_back_every_running_job(two):
    wk, _, client, procs = two
    wk.stop()
    assert sorted(client.returned()) == ['a' + '0' * 11, 'b' + '0' * 11]
    assert all(t.state == 'handed back' for t in wk.tasks.values())
    assert all(p.wait(timeout=10) is not None for p in procs)


def test_a_score_job_gets_all_the_cores_the_rule_allows_not_a_slots_share(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'cpus', lambda: 16)
    wk = worker.Worker(Queue(), tmp_path, slots=2, rules=Rules())  # type: ignore[arg-type]
    assert wk.threads == 4 and wk.whole == 8
    s = job('s', score=True)['spec'] | {'seed': 1, 'trusted': True,
                                        'score': {'game': 'tree', 'episodes': 8, 'baselines': ['random']}}
    cmd = wk.score_command(s, {'world': tmp_path / 'w.toml', 'parent': tmp_path / 'b.pt'}, tmp_path, tmp_path / 'g.json')
    assert cmd[cmd.index('--processes') + 1] == '8'
    assert worker.shares(2, Rules(), None) == (4, 3) and worker.shares(1, Rules(), None) == (8, 7)


# calibrate


def reading(sps, ram=4.0, vram=None):
    return {'sps': sps, 'ram_gb': ram, 'vram_gb': vram}


def test_two_slots_need_a_fifth_more_samples_and_room_in_memory():
    assert calibrate.decide(reading(10_000), reading(16_000, 20), 36)[0] == 2
    # 1.2x exactly is enough, just under is not
    assert calibrate.decide(reading(10_000), reading(12_000), 36)[0] == 2
    slots, why = calibrate.decide(reading(10_000), reading(11_900), 36)
    assert slots == 1 and '1.19x' in why
    # a CPU box that is update-bound gains nothing
    assert calibrate.decide(reading(1_000), reading(1_050), 32)[0] == 1
    # memory: under 60% of the machine's RAM
    assert calibrate.decide(reading(10_000), reading(16_000, 21.5), 36)[0] == 2
    slots, why = calibrate.decide(reading(10_000), reading(16_000, 21.7), 36)
    assert slots == 1 and 'memory' in why
    # VRAM on CUDA: under 80% of the card
    assert calibrate.decide(reading(10_000, vram=2), reading(16_000, vram=4.7), 36, 6)[0] == 2
    slots, why = calibrate.decide(reading(10_000, vram=2), reading(16_000, vram=4.9), 36, 6)
    assert slots == 1 and 'GPU memory' in why
    # no readings (a run that never finished an update) is not a reason to double up
    assert calibrate.decide(reading(0), reading(0), 36)[0] == 1


def test_slots_come_from_the_flag_then_a_calibration_for_this_machine_else_one(tmp_path):
    ident = calibrate.identity({'gpus': [{'name': 'RTX', 'memory_gb': 4}], 'cores': 16, 'memory_gb': 32}, 0.5)
    assert calibrate.choose(None, tmp_path, ident, 12)[:1] == (1,) and not calibrate.choose(None, tmp_path, ident, 12)[2]
    saved = {'slots': 2, 'why': 'ok', 'date': '2026-11-05', 'version': 12, 'machine': ident}
    (tmp_path / calibrate.FILE).write_text(json.dumps(saved))
    slots, why, fresh = calibrate.choose(None, tmp_path, ident, 12)
    assert (slots, fresh) == (2, True) and '2026-11-05' in why
    assert calibrate.choose(3, tmp_path, ident, 12) == (3, '--slots 3', True)
    # other hardware, or another cpu share: back to one, and say to calibrate again
    other = calibrate.identity({'gpus': [], 'cores': 8, 'memory_gb': 16}, 0.5)
    slots, why, fresh = calibrate.choose(None, tmp_path, other, 12)
    assert (slots, fresh) == (1, False) and 'again' in why
    # the same machine at another cpu share names both, and the flags that set it
    slots, why, fresh = calibrate.choose(None, tmp_path, calibrate.identity({'gpus': [{'name': 'RTX', 'memory_gb': 4}],
                                                                           'cores': 16, 'memory_gb': 32}, 1.0), 12)
    assert (slots, fresh) == (1, False) and 'share 0.5' in why and 'at 1.0' in why and '--anytime' in why
    # a newer worker keeps the number but says so
    slots, why, fresh = calibrate.choose(None, tmp_path, ident, 13)
    assert (slots, fresh) == (2, False) and 'by worker 12' in why


def test_a_runs_speed_is_the_middle_of_its_updates_after_the_first_few(tmp_path):
    run = tmp_path / '20261105-100000-x'
    run.mkdir(parents=True)
    rows = [100, 100, 9, 10, 11, 5000]
    (run / 'metrics.jsonl').write_text('\n'.join(json.dumps({'samples_per_second': r}) for r in rows) + '\n')
    assert calibrate.sps_of(tmp_path) == 10.5
    assert calibrate.sps_of(tmp_path / 'none') == 0.0


def test_calibrating_measures_alone_then_a_pair_and_saves_the_decision(tmp_path, monkeypatch):
    seen = []

    def measure(commands, roots, cwd, threads, seconds, say=print):
        seen.append((commands, threads, seconds))
        return {'sps': 10_000 * (1 if len(commands) == 1 else 1.6), 'ram_gb': 3.0 * len(commands), 'vram_gb': None,
                'seconds': seconds}

    monkeypatch.setattr(calibrate, 'measure', measure)
    sim = tmp_path
    (tmp_path / 'home').mkdir()
    specs = {'gpus': [], 'mps': True, 'cores': 8, 'memory_gb': 24}
    rec = calibrate.run(tmp_path / 'home', sim, Path(sys.executable), Rules(), specs,
                        lambda n: (4 // n, 3 if n == 1 else 1), lambda cmd, n: cmd, 12, seconds=7)
    assert rec['slots'] == 2 and rec['gain'] == 1.6 and rec['version'] == 12
    (alone,), (first, second) = seen[0][0], seen[1][0]
    assert alone[alone.index('--workers') + 1] == '3' and first[first.index('--workers') + 1] == '1'
    assert first[first.index('--world') + 1] == calibrate.WORLD and '--no-evals' in first and '--scratch' in first
    assert first[first.index('--memory') + 1] == str(calibrate.MEMORY) and rec['memory'] == calibrate.MEMORY
    assert first[first.index('--root') + 1] != second[second.index('--root') + 1]
    assert [s[1] for s in seen] == [4, 2] and seen[0][2] == 7
    assert json.loads((tmp_path / 'home' / calibrate.FILE).read_text()) == rec
    # the scratch folders for the runs are gone
    assert list((tmp_path / 'home').glob('calibrate-*')) == []


def test_calibrating_can_be_pointed_at_another_world_config_and_memory(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(calibrate, 'measure', lambda commands, *a, **k: seen.append(commands) or
                        {'sps': 100, 'ram_gb': 1.0, 'vram_gb': None, 'seconds': 1})
    (tmp_path / 'home').mkdir()
    rec = calibrate.run(tmp_path / 'home', tmp_path, Path(sys.executable), Rules(), {'memory_gb': 24},
                        lambda n: (2, 1), lambda cmd, n: cmd, 12, seconds=1, world='/w.toml', train='/t.toml', memory=64)
    cmd = seen[0][0]
    assert [cmd[cmd.index(f) + 1] for f in ('--world', '--train', '--memory')] == ['/w.toml', '/t.toml', '64']
    assert (rec['world'], rec['train'], rec['memory']) == ('/w.toml', '/t.toml', 64)
