# How hard a machine trains: what the GPU and CPU do while a run collects and while it updates, read every couple of
# seconds by a thread in train and written into each metrics row, so every run says where its time went, wherever it
# trained (the Mac, a pod, a lent machine). held_back() turns a run's rows into what's holding it back, in plain
# words; the worker sends that with its status, and this prints it for runs on disk:
#
#   uv run python -m terrarium.usage RUN [RUN ...]
#
# GPU busy is the share of time the GPU had work (nvidia-smi's `utilization.gpu`, Apple's `Device Utilization %`), not how
# much of it the work filled: a GPU fed one small step at a time can show busy and still be mostly waiting.

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import psutil

EVERY = 2.0
# rows a status report averages over, about the last minute on most machines
RECENT = 10
PHASES = ('collect', 'update')


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def number(text: str) -> float | None:
    return float(text) if re.fullmatch(r'\d+(\.\d+)?', text.strip()) else None


class Gpu:
    """The GPU training uses: busy share, memory in use and, where the driver says, power against its limit."""

    def __init__(self, device: str):
        self.smi = shutil.which('nvidia-smi') if device == 'cuda' else None
        self.apple = device == 'mps' and sys.platform == 'darwin'
        visible = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')[0].strip()
        self.index = int(visible) if visible.isdigit() else 0

    def read(self) -> dict:
        if self.smi:
            out = run([self.smi, f'--id={self.index}', '--query-gpu=utilization.gpu,memory.used,power.draw,power.limit',
                       '--format=csv,noheader,nounits'])
            cols = [number(c) for c in out.split(',')] if out.count(',') == 3 else [None] * 4
            busy, mb, watts, limit = cols
            return {'gpu_busy': busy / 100 if busy is not None else None, 'gpu_gb': mb / 1024 if mb is not None else None,
                    'gpu_power': watts / limit if watts is not None and limit else None}
        if self.apple:
            out = run(['ioreg', '-r', '-d', '1', '-c', 'IOAccelerator'])
            busy = re.search(r'"Device Utilization %"=(\d+)', out)
            used = re.search(r'"In use system memory"=(\d+)', out)
            return {'gpu_busy': int(busy.group(1)) / 100 if busy else None,
                    'gpu_gb': int(used.group(1)) / 2**30 if used else None, 'gpu_power': None}
        return {}


class Sampler:
    """Reads the GPU and this process tree's CPU every EVERY seconds, filed under whichever phase training is in."""

    def __init__(self, device: str):
        self.gpu = Gpu(device)
        self.me = psutil.Process()
        self.procs: dict[int, psutil.Process] = {}
        self.phase: str | None = None
        self.sums: dict[str, dict[str, list[float]]] = {}
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, name='usage', daemon=True)

    def start(self) -> 'Sampler':
        psutil.cpu_percent()
        self.thread.start()
        return self

    def stop(self):
        self.stopping.set()

    def into(self, phase: str | None):
        self.phase = phase

    def cores(self) -> float:
        """Cores busy in this process and everything it started (the rollout processes), since the last call."""
        try:
            tree = [self.me, *self.me.children(recursive=True)]
        except psutil.Error:
            return 0.0
        busy = 0.0
        for p in tree:
            # the first reading of a process is always 0; keep it so the next one covers the time between
            kept = self.procs.setdefault(p.pid, p)
            try:
                busy += kept.cpu_percent()
            except psutil.Error:
                self.procs.pop(p.pid, None)
        return busy / 100

    def loop(self):
        while not self.stopping.wait(EVERY):
            phase = self.phase
            reading = {'cpu_cores': self.cores(), 'machine_cpu': psutil.cpu_percent() / 100, **self.gpu.read()}
            if phase is None:
                continue
            with self.lock:
                bucket = self.sums.setdefault(phase, {})
                for key, value in reading.items():
                    if value is not None:
                        bucket.setdefault(key, []).append(value)

    def take(self) -> dict:
        """Means since the last take, for a metrics row: gpu_busy_collect, cpu_cores_update and so on. A phase
        shorter than EVERY may have no reading; over a few rows they even out by how long each phase takes."""
        with self.lock:
            sums, self.sums = self.sums, {}
        row = {}
        for phase, bucket in sums.items():
            for key, values in bucket.items():
                row[f'{key}_{phase}'] = round(sum(values) / len(values), 3)
        return row


def mean(rows: list[dict], key: str) -> float | None:
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return sum(values) / len(values) if values else None


def recent(rows: list[dict], n: int = RECENT) -> dict:
    """The last n rows' times and readings, averaged: what a status report sends."""
    rows = [r for r in rows if 'collect_seconds' in r][-n:]
    keys = ['samples_per_second', 'collect_seconds', 'update_seconds',
            *(f'{k}_{p}' for k in ('gpu_busy', 'gpu_gb', 'gpu_power', 'cpu_cores', 'machine_cpu') for p in PHASES)]
    return {k: round(v, 3) for k in keys if (v := mean(rows, k)) is not None}


def held_back(u: dict, record: dict) -> str:
    """What's holding training back, from recent() and the run's run.json: one plain sentence."""
    c, up = u.get('collect_seconds'), u.get('update_seconds')
    if not c or not up:
        return 'not enough rounds yet to tell'
    share = c / (c + up)
    busy_c, busy_u = u.get('gpu_busy_collect'), u.get('gpu_busy_update')
    workers, device = record.get('workers') or 1, record.get('device')
    machine = max(u.get('machine_cpu_collect') or 0, u.get('machine_cpu_update') or 0)
    if busy_c is not None and busy_u is not None and (busy_c * c + busy_u * up) / (c + up) >= 0.85:
        return 'the GPU itself: it has work nearly all the time, so only a faster GPU goes quicker'
    if share >= 0.5:
        if record.get('gpu_collect'):
            return (f'collecting ({share:.0%} of each round): the worlds step on the CPU between brain passes; '
                    'more rollout processes, if the CPU has room')
        cores = u.get('cpu_cores_collect')
        if cores is not None and cores >= 0.8 * workers:
            spare = 'and the machine has cores to spare: more rollout processes would help' if machine < 0.75 else \
                'and the CPU is full'
            return f'collecting ({share:.0%} of each round): all {workers} rollout processes are busy, {spare}'
        return f'collecting ({share:.0%} of each round)'
    if device == 'cpu':
        return f'the update ({1 - share:.0%} of each round), on the CPU: there is no GPU'
    if busy_u is not None and busy_u < 0.6:
        return (f'the update ({1 - share:.0%} of each round), with the GPU idle {1 - busy_u:.0%} of it: it waits on '
                'Python handing it small steps one at a time, so the CPU core running train sets the pace')
    if busy_u is not None:
        return f'the update ({1 - share:.0%} of each round), on a GPU busy through it: the GPU\'s speed'
    return f'the update ({1 - share:.0%} of each round)'


def rows_of(run: Path) -> list[dict]:
    rows = []
    for line in (run / 'metrics.jsonl').read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def pct(v: float | None) -> str:
    return '–' if v is None else f'{v:.0%}'


def show(run: Path) -> str:
    record = json.loads((run / 'run.json').read_text())
    u = recent(rows_of(run), 40)
    m = record.get('machine') or {}
    where = record.get('gpu') or (m.get('cpu') if record.get('device') != 'mps' else f'{m.get("cpu")} GPU')
    c, up = u.get('collect_seconds'), u.get('update_seconds')
    cores = '/'.join('–' if (v := u.get(f'cpu_cores_{p}')) is None else f'{v:.1f}' for p in PHASES)
    return (f'{run.name}\n  {where}, {record.get("workers")} rollout processes, {record.get("threads")} threads'
            f'{", --gpu-collect" if record.get("gpu_collect") else ""}\n'
            f'  {u.get("samples_per_second", 0):,.0f} samples/s; collect {c or 0:.2f} s, update {up or 0:.2f} s a round\n'
            f'  GPU busy {pct(u.get("gpu_busy_collect"))} collecting, {pct(u.get("gpu_busy_update"))} updating; '
            f'cores busy {cores} (collect/update)\n'
            f'  held back by {held_back(u, record)}')


def main():
    parser = argparse.ArgumentParser(description='where a run\'s training time goes, and what holds it back')
    parser.add_argument('runs', nargs='+', type=Path)
    args = parser.parse_args()
    for run in args.runs:
        if (run / 'run.json').exists() and (run / 'metrics.jsonl').exists():
            print(show(run))


if __name__ == '__main__':
    main()
