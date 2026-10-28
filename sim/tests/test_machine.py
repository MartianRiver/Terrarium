import io
import json
import random
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import psutil
import pytest

from terrarium import jobs, machine, worker
from terrarium.machine import Rules, Seen, Watch

QUIET = Seen(idle=3600, plugged=True, temp=60, others=(0.0, 0.0), fullscreen=False)


class Fake:
    def __init__(self, seen: Seen = QUIET):
        self.seen = seen

    def read(self, ours):
        return self.seen


def watch(rules=Rules(), **seen) -> tuple[Watch, Fake]:
    fake = Fake(QUIET._replace(**seen))
    return Watch(rules, fake), fake  # type: ignore[arg-type]


def test_a_quiet_machine_on_mains_may_train():
    w, _ = watch()
    assert w.check().action == 'go'


def test_someone_at_the_machine_or_on_battery_pauses_it():
    w, fake = watch(idle=120)
    assert w.check() == ('pause', 'in use (idle 2 of 10 min)')
    fake.seen = QUIET._replace(plugged=False)
    assert w.check().reason == 'on battery'
    assert watch(Rules(cooldown=0), idle=0)[0].check().action == 'go'
    assert watch(Rules(battery=True), plugged=False)[0].check().action == 'go'
    # no battery, or an idle time it can't read (Linux), doesn't hold it up
    assert watch(plugged=None, idle=None)[0].check().action == 'go'


def test_a_hot_gpu_pauses_until_it_has_cooled_a_little():
    w, fake = watch(temp=86)
    assert w.check().reason == 'GPU at 86 °C'
    fake.seen = QUIET._replace(temp=82)
    assert w.check().action == 'pause'
    fake.seen = QUIET._replace(temp=79)
    assert w.check().action == 'go'
    assert watch(Rules(gpu_temp=0), temp=95)[0].check().action == 'go'


def test_a_game_on_the_gpu_stops_a_job_after_ten_seconds_and_keeps_new_ones_from_starting():
    w, fake = watch(others=(0.5, 0.2))
    assert w.check(now=0).action == 'stop'
    ours = frozenset({1})
    assert w.check(ours, now=1).action == 'go'
    assert w.check(ours, now=1 + machine.OTHERS_SECONDS).action == 'stop'
    fake.seen = QUIET._replace(others=(0.0, 1.5))
    w.busy_since = None
    assert w.check(ours, now=100).action == 'go' and w.check(ours, now=111).action == 'stop'
    fake.seen = QUIET._replace(fullscreen=True)
    assert w.check(ours, now=200) == ('stop', 'something is running full screen')
    assert watch(Rules(share_gpu=True), others=(1.0, 4.0), fullscreen=True)[0].check(ours).action == 'go'


def test_a_rented_machine_never_reads_anything():
    assert Watch(Rules.anytime()).check() == ('go', 'rented: no rules')


def test_settings_load_strictly_and_flags_win(tmp_path):
    path = tmp_path / 'settings.toml'
    assert machine.load(path) == Rules()
    path.write_text('cooldown = 0\ncpu = 0.75\nbattery = true\n')
    assert machine.load(path, cpu=0.25) == Rules(cooldown=0, cpu=0.25, battery=True)
    for bad, match in [('gpu = 1\n', 'unknown setting'), ('battery = 1\n', 'should be bool'),
                       ('cooldown = "10"\n', 'should be float'), ('cpu = 1.5\n', 'share of the cores')]:
        path.write_text(bad)
        with pytest.raises(ValueError, match=match):
            machine.load(path)


def test_gpu_counters_count_other_programs_on_the_nvidia_adapter_but_not_ours_or_the_desktop():
    nvidia, intel = '0x00000000_0x0000d1a3', '0x00000000_0x00009f21'
    engines = [(f'pid_10_luid_{nvidia}_phys_0_eng_0_engtype_3D', 30.0),
               (f'pid_10_luid_{nvidia}_phys_0_eng_1_engtype_3D', 15.0),
               (f'pid_11_luid_{intel}_phys_0_eng_0_engtype_3D', 90.0),
               (f'pid_12_luid_{nvidia}_phys_0_eng_0_engtype_3D', 80.0),
               (f'pid_13_luid_{nvidia}_phys_0_eng_0_engtype_3D', 70.0),
               (f'pid_10_luid_{nvidia}_phys_0_eng_5_engtype_VideoDecode', 50.0)]
    memory = [(f'pid_10_luid_{nvidia}_phys_0', 2.0**30), (f'pid_12_luid_{nvidia}_phys_0', 3 * 2.0**30),
              (f'pid_14_luid_{nvidia}_phys_0', 2.0**29)]
    names = {12: 'dwm.exe'}.get
    share, gb = machine.gpu_use(engines, memory, {nvidia}, frozenset({13}), lambda pid: names(pid, 'game.exe'))
    assert share == pytest.approx(0.45) and gb == pytest.approx(1.5)
    # adapter ids that match none of the counters' count every adapter, so a game is never missed
    share, _ = machine.gpu_use(engines, memory, {'0x1_0x2'}, frozenset(), lambda pid: 'x.exe')
    assert share == pytest.approx(0.9)


def test_nvidia_smi_pmon_is_read_by_its_header():
    text = ('# gpu         pid   type     sm    mem    enc    dec    jpg    ofa     fb   ccpm    command\n'
            '# Idx           #    C/G      %      %      %      %      %      %     MB     MB    name\n'
            '    0       1234     G     35      4      -      -      -      -    900      0    game\n'
            '    0       4321     C     90     20      -      -      -      -   2048      0    python\n'
            '    0          -     -      -      -      -      -      -      -      -      -    -\n')
    assert machine.pmon(text, frozenset({4321})) == (0.35, pytest.approx(900 / 1024))
    assert machine.pmon('nvidia-smi: not supported', frozenset()) is None


def test_a_second_stop_signal_cannot_cut_the_hand_back_short():
    old = {s: signal.getsignal(s) for s in worker.STOPS}
    try:
        signal.signal(signal.SIGTERM, worker.interrupt)
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGTERM)
        assert all(signal.getsignal(s) == signal.SIG_IGN for s in worker.STOPS)
        signal.raise_signal(signal.SIGTERM)
    finally:
        for s, handler in old.items():
            signal.signal(s, handler)


class Client:
    def __init__(self):
        self.calls = []

    def json(self, method, path, body=None):
        self.calls.append(path)


@pytest.fixture
def running(tmp_path):
    """A worker with one job training (a sleeping process) on a machine it reads through a Fake."""
    client, (w, fake) = Client(), watch()
    wk = worker.Worker(client, tmp_path, rules=Rules(), watch=w)  # type: ignore[arg-type]
    task = worker.Task({'spec': {'id': 'a' * 12, 'name': 'n', 'batch': 'b', 'samples': 64}, 'sig': ''})
    proc = task.proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    task.state = 'training'
    wk.tasks[task.id] = task
    yield wk, task, proc, fake, client
    if proc.poll() is None:
        proc.kill()


def test_the_worker_pauses_resumes_and_hands_back_a_running_job(running):
    wk, task, proc, fake, client = running
    fake.seen = QUIET._replace(idle=5)
    wk.mind(now=1000)
    assert task.state == 'paused' and task.progress()['reason'].startswith('in use')
    assert machine.tree(proc.pid)[0].status() == 'stopped' or sys.platform == 'win32'
    assert wk.state() == ('working', 'in use (idle 0 of 10 min)') and not wk.wants_work()
    fake.seen = QUIET
    wk.mind(now=1100)
    assert task.state == 'training' and task.paused == 100
    fake.seen = QUIET._replace(plugged=False)
    wk.mind(now=2000)
    wk.mind(now=2000 + 30 * 60 + 1)
    assert task.state == 'handed back' and task.gone.is_set()
    assert client.calls == [f'/api/jobs/{task.id}/return']
    assert proc.wait(timeout=10) is not None


def test_a_game_hands_the_job_back_straight_away(running):
    wk, task, proc, fake, _ = running
    fake.seen = QUIET._replace(fullscreen=True)
    wk.mind()
    assert task.state == 'handed back' and task.reason == 'something is running full screen'
    assert wk.state() == ('working', 'something is running full screen')
    assert proc.wait(timeout=10) is not None


class Holds:
    def __init__(self):
        self.calls = []

    def hold(self, on):
        self.calls.append(on)


def test_the_machine_is_kept_awake_while_a_job_trains_but_not_while_it_is_paused(running):
    wk, task, _, fake, _ = running
    wk.awake = holds = Holds()
    wk.mind(now=1000)
    fake.seen = QUIET._replace(plugged=False)
    wk.mind(now=1010)
    wk.rules = Rules(keep_awake=False)
    fake.seen = QUIET
    wk.mind(now=1020)
    assert holds.calls == [True, False, False] and task.state == 'training'
    assert Rules.anytime().keep_awake is False


def test_a_job_taken_away_ends_with_everything_it_started(tmp_path):
    class Taken(Client):
        def json(self, method, path, body=None):
            raise RuntimeError(f'{method} {path}: 410 not yours any more')

    wk = worker.Worker(Taken(), tmp_path, rules=Rules(), watch=watch()[0])  # type: ignore[arg-type]
    task = worker.Task({'spec': {'id': 'b' * 12, 'name': 'n', 'batch': 'b', 'samples': 64}, 'sig': ''})
    # a training run with a rollout process of its own, as train starts them
    task.proc = subprocess.Popen([sys.executable, '-c', 'import subprocess, sys, time; '
                                  'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]); time.sleep(60)'])
    wk.tasks[task.id] = task
    family = machine.tree(task.proc.pid)
    for _ in range(50):
        if len(family) == 2:
            break
        time.sleep(0.1)
        family = machine.tree(task.proc.pid)
    assert len(family) == 2
    wk.beat()
    assert task.gone.is_set()
    assert all(not p.is_running() or p.status() == psutil.STATUS_ZOMBIE for p in family)


def test_cores_are_shared_out_by_the_cpu_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'cpus', lambda: 16)
    half = worker.Worker(Client(), tmp_path, rules=Rules())  # type: ignore[arg-type]
    full = worker.Worker(Client(), tmp_path, rules=Rules.anytime())  # type: ignore[arg-type]
    assert (half.threads, half.rollouts) == (8, 7) and (full.threads, full.rollouts) == (16, 8)


def test_kept_runs_stay_under_their_space_oldest_going_first(tmp_path):
    for name in ('20261020-000000-a', '20261021-000000-b', '20261022-000000-c'):
        (tmp_path / name / 'checkpoints').mkdir(parents=True)
        (tmp_path / name / 'checkpoints' / 'x.pt').write_bytes(b'x' * 400)
    worker.prune(tmp_path, 900 / 2**30)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['20261021-000000-b', '20261022-000000-c']


def test_paused_time_goes_into_the_run_record_and_out_of_its_hours(tmp_path):
    from terrarium import compute
    run = tmp_path / '20261025-100000-n'
    run.mkdir()
    (run / 'run.json').write_text(json.dumps({'started': '2026-10-25T10:00:00+1100',
                                              'finished': '2026-10-25T11:00:00+1100'}))
    worker.pack(run, paused=600.4)
    assert json.loads((run / 'run.json').read_text())['paused'] == 600
    assert compute.seconds(run) == 3000


def test_a_token_saved_by_windows_powershell_still_reads(tmp_path):
    path = tmp_path / 'token'
    path.write_bytes('abc123\r\n'.encode('utf-16'))
    assert jobs.token(path) == 'abc123'
    path.write_bytes(b'\xef\xbb\xbfabc123\n')
    assert jobs.token(path) == 'abc123'


def test_load_is_read_where_os_has_none(tmp_path, monkeypatch):
    wk = worker.Worker(Client(), tmp_path, max_load=1.0)  # type: ignore[arg-type]
    monkeypatch.setattr(worker.psutil, 'getloadavg', lambda: (5.0, 0, 0))
    assert not wk.wants_work()
    monkeypatch.setattr(worker.psutil, 'getloadavg', lambda: (0.5, 0, 0))
    assert wk.wants_work()



def test_a_result_too_big_for_the_coordinator_leaves_checkpoints_out_but_never_the_last(tmp_path):
    run = tmp_path / '20261028-100000-n'
    (run / 'checkpoints').mkdir(parents=True)
    (run / 'run.json').write_text(json.dumps({'checkpoint': '00000000009.pt'}))
    names = [f'{i:011d}.pt' for i in range(10)]
    for i, name in enumerate(names):
        (run / 'checkpoints' / name).write_bytes(random.Random(i).randbytes(1000))
    data = worker.pack(run, limit=3500)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        sent = sorted(Path(m.name).name for m in tar.getmembers() if m.name.endswith('.pt'))
        record = json.load(tar.extractfile(f'{run.name}/run.json'))  # type: ignore[arg-type]
    assert len(data) <= 3500 and sent[-1] == names[-1] and 1 < len(sent) < 10
    assert record['checkpoints_left_out'] == 10 - len(sent)
    # what's kept here is the whole run
    assert len(list((run / 'checkpoints').iterdir())) == 10
    assert 'checkpoints_left_out' not in json.loads((run / 'run.json').read_text())
    # a brain bigger than the limit by itself still goes, and the coordinator says no
    with tarfile.open(fileobj=io.BytesIO(worker.pack(run, limit=10)), mode='r:gz') as tar:
        assert [Path(m.name).name for m in tar.getmembers() if m.name.endswith('.pt')] == [names[-1]]
