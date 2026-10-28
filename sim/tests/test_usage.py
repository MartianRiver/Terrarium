import time

from terrarium import usage


def test_readings_are_filed_under_the_phase_training_is_in(monkeypatch):
    monkeypatch.setattr(usage, 'EVERY', 0.01)
    sampler = usage.Sampler('cpu')
    busy = iter([0.2, 0.8] * 1000)
    monkeypatch.setattr(sampler.gpu, 'read', lambda: {'gpu_busy': next(busy), 'gpu_power': None})
    sampler.start()
    try:
        sampler.into('update')
        time.sleep(0.3)
        sampler.into(None)
        time.sleep(0.05)
        row = sampler.take()
    finally:
        sampler.stop()
    assert set(row) == {'gpu_busy_update', 'cpu_cores_update', 'machine_cpu_update'}
    assert 0.2 <= row['gpu_busy_update'] <= 0.8
    # taken means cleared, and readings outside a phase are dropped
    assert sampler.take() == {}


def test_nvidia_smi_is_read_and_a_power_it_cant_tell_is_left_out(monkeypatch):
    gpu = usage.Gpu('cpu')
    gpu.smi = 'nvidia-smi'
    monkeypatch.setattr(usage, 'run', lambda cmd: '87, 2048, [N/A], [N/A]\n')
    assert gpu.read() == {'gpu_busy': 0.87, 'gpu_gb': 2.0, 'gpu_power': None}
    monkeypatch.setattr(usage, 'run', lambda cmd: '')
    assert gpu.read() == {'gpu_busy': None, 'gpu_gb': None, 'gpu_power': None}


def test_recent_averages_the_last_rounds():
    rows = [{'update': 1}] + [{'collect_seconds': 1.0, 'update_seconds': float(u), 'samples_per_second': 100,
                                'gpu_busy_update': 0.5} for u in range(20)]
    got = usage.recent(rows, 4)
    assert got['update_seconds'] == 17.5 and got['gpu_busy_update'] == 0.5 and 'gpu_busy_collect' not in got


def test_what_holds_training_back():
    cuda = {'device': 'cuda', 'workers': 6}
    gpu_bound = {'collect_seconds': 1, 'update_seconds': 3, 'gpu_busy_collect': 0.7, 'gpu_busy_update': 0.95}
    assert usage.held_back(gpu_bound, cuda).startswith('the GPU itself')
    slow_collect = {'collect_seconds': 3, 'update_seconds': 1, 'cpu_cores_collect': 5.8, 'machine_cpu_collect': 0.4}
    assert 'more rollout processes would help' in usage.held_back(slow_collect, cuda)
    assert 'the CPU is full' in usage.held_back(slow_collect | {'machine_cpu_collect': 0.95}, cuda)
    waiting = {'collect_seconds': 1, 'update_seconds': 4, 'gpu_busy_collect': 0.0, 'gpu_busy_update': 0.4}
    assert 'waits on Python' in usage.held_back(waiting, cuda)
    assert 'on the CPU' in usage.held_back({'collect_seconds': 1, 'update_seconds': 4}, {'device': 'cpu'})
    assert usage.held_back({}, cuda) == 'not enough rounds yet to tell'
