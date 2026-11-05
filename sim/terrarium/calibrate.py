# How many training jobs a machine should run at once (docs/compute.md, "Slots").
#
#   uv run python -m terrarium.worker calibrate [--world W] [--train T] [--memory N] [--cpu SHARE] [--anytime]
#
# One PPO run leaves the CPU (collecting) and the GPU (updating) each part idle, so
# two at once can add up to more samples a second than one alone; a box that is
# update-bound on its CPU gains nothing. So it's measured per machine: a short
# training run alone, then two at once, each as the worker would start it. Two
# slots when the pair trains >= GAIN times as fast and fits in memory, else one.
# The result is saved in the worker's home and read by `worker run`.
#
# It trains what our lines run: a fresh brain with notes (a GRU), which spends most of
# its time in updates, in the tree world. A brain without memory in the tiny solo
# world fills the machine alone and read 1.05x on the Mac where real memory runs gave 1.5x.

import json
import shutil
import statistics
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Callable

import psutil

from . import machine, usage
from .log import Logger
from .trust import job_env

log = Logger('calibrate')

# a fresh brain, so it needs no parent and no network
WORLD, TRAIN, MEMORY = 'configs/nursery-tree-home.toml', 'configs/train.toml', 128
SECONDS = 150
# the first updates include starting up
SKIP = 2
GAIN = 1.2
RAM_SHARE = 0.6
VRAM_SHARE = 0.8
FILE = 'calibration.json'


def decide(alone: dict, pair: dict, memory_gb: float, vram_gb: float | None = None) -> tuple[int, str]:
    # each reading is {'sps', 'ram_gb', 'vram_gb'}; the pair's sps is the two runs' total
    if not alone.get('sps') or not pair.get('sps'):
        return 1, 'no readings from a run, so one slot'
    gain = pair['sps'] / alone['sps']
    if gain < GAIN:
        return 1, f'two at once train {gain:.2f}x as fast as one, under {GAIN}x'
    if pair['ram_gb'] >= RAM_SHARE * memory_gb:
        return 1, f'two runs peak at {pair["ram_gb"]:.1f} GB of {memory_gb:g} GB of memory, over {RAM_SHARE:.0%}'
    if vram_gb and pair.get('vram_gb') is not None and pair['vram_gb'] >= VRAM_SHARE * vram_gb:
        return 1, f'two runs peak at {pair["vram_gb"]:.1f} GB of {vram_gb:g} GB of GPU memory, over {VRAM_SHARE:.0%}'
    return 2, f'two at once train {gain:.2f}x as fast as one, within memory'


def identity(specs: dict, cpu_share: float) -> dict:
    return {'gpus': [g['name'] for g in specs.get('gpus', [])], 'mps': bool(specs.get('mps')),
            'cores': specs.get('cores'), 'memory_gb': specs.get('memory_gb'), 'cpu_share': cpu_share}


def load(home: Path) -> dict | None:
    try:
        return json.loads((home / FILE).read_text())
    except (OSError, ValueError):
        return None


def choose(given: int | None, home: Path, ident: dict, version: int) -> tuple[int, str, bool]:
    # (slots, what to say, False if it should be calibrated again): --slots, else the saved answer for this hardware
    if given is not None:
        return given, f'--slots {given}', True
    saved = load(home)
    if saved is None:
        return 1, 'no calibration yet: `worker calibrate` finds out whether this machine gains from running two', False
    if saved.get('machine') != ident:
        return 1, 'the saved calibration is for other hardware or another cpu share: run `worker calibrate` again', False
    why = f'calibrated {saved["date"]}: {saved["why"]}'
    if saved.get('version') != version:
        return saved['slots'], why + f' (by worker {saved.get("version")}, this is {version}: run `worker calibrate` again)', False
    return saved['slots'], why, True


def gpu_gb() -> float | None:
    out = machine.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits', '-i', '0']).strip()
    return int(out) / 1024 if out.isdigit() else None


def rss_gb(procs: list[subprocess.Popen]) -> float:
    total = 0
    for proc in procs:
        for p in machine.tree(proc.pid):
            try:
                total += p.memory_info().rss
            except psutil.Error:
                pass  # a rollout process that ended between the listing and the reading
    return total / 2**30


def sps_of(root: Path) -> float:
    runs = list(root.glob('*/metrics.jsonl'))
    rows = [r['samples_per_second'] for r in usage.rows_of(runs[0].parent) if 'samples_per_second' in r] if runs else []
    return float(statistics.median(rows[SKIP:] or rows)) if rows else 0.0


def measure(commands: list[list[str]], roots: list[Path], cwd: Path, threads: int, seconds: float,
            say: Callable[[str], None] = print) -> dict:
    # combined samples a second, and the most memory held at once (RAM, and the GPU's on CUDA)
    env = job_env(OMP_NUM_THREADS=str(threads), PYTHONUNBUFFERED='1')
    procs, logs = [], []
    for i, cmd in enumerate(commands):
        roots[i].mkdir(parents=True, exist_ok=True)
        logs.append(open(roots[i] / 'train.log', 'wb'))
        procs.append(subprocess.Popen(cmd, cwd=cwd, stdout=logs[-1], stderr=subprocess.STDOUT, env=env))
    ram, vram, started = 0.0, None, time.time()
    try:
        while time.time() - started < seconds:
            time.sleep(2)
            ram = max(ram, rss_gb(procs))
            if (used := gpu_gb()) is not None:
                vram = max(vram or 0.0, used)
            for i, proc in enumerate(procs):
                if proc.poll() not in (None, 0):
                    tail = (roots[i] / 'train.log').read_text(errors='replace').splitlines()[-15:]
                    raise RuntimeError('a calibration run exited early:\n' + '\n'.join(tail))
            if all(proc.poll() == 0 for proc in procs):
                break
    finally:
        for proc in procs:
            machine.kill(proc.pid)
        for f in logs:
            f.close()
    return {'sps': round(sum(sps_of(r) for r in roots)), 'ram_gb': round(ram, 2),
            'vram_gb': None if vram is None else round(vram, 2), 'seconds': round(time.time() - started)}


def run(home: Path, sim: Path, python: Path, rules: machine.Rules, specs: dict,
        split: Callable[[int], tuple[int, int]], cap: Callable[[list[str], int], list[str]], version: int,
        seconds: float = SECONDS, world: str = WORLD, train: str = TRAIN, memory: int = MEMORY) -> dict:
    # split(n): threads and rollout processes each of n jobs gets; cap(cmd, n): the CPU cap on one, as the worker gives them
    info = subprocess.run([str(python), '-c', 'import torch; from terrarium.train import best_device; '
                           'print(torch.__version__, best_device())'], cwd=sim, capture_output=True, text=True)
    torch_version, _, device = info.stdout.strip().partition(' ')
    work = Path(tempfile.mkdtemp(prefix='calibrate-', dir=home))
    phases = {}
    try:
        for n, name in ((1, 'alone'), (2, 'pair')):
            threads, rollouts = split(n)
            roots = [work / name / str(i) for i in range(n)]
            cmds = [cap([str(python), '-m', 'terrarium.train', f'calibrate-{name}-{i}', '--world', world,
                         '--train', train, '--memory', str(memory), '--seed', str(i), '--scratch', '--no-evals',
                         '--workers', str(rollouts), '--root', str(roots[i])], n) for i in range(n)]
            print(f'{name}: {n} run{"s" if n > 1 else ""}, {threads} threads and {rollouts} rollout processes each, '
                  f'{seconds:g} s', flush=True)
            phases[name] = measure(cmds, roots, sim, threads, seconds)
            print(f'  {phases[name]}', flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    ram = specs.get('memory_gb') or 0
    vram = (specs.get('gpus') or [{}])[0].get('memory_gb')
    slots, why = decide(phases['alone'], phases['pair'], ram, vram)
    record = {'slots': slots, 'why': why, 'date': date.today().isoformat(), 'version': version, 'torch': torch_version,
              'device': device, 'machine': identity(specs, rules.cpu), 'alone': phases['alone'],
              'pair': phases['pair'], 'gain': round(phases['pair']['sps'] / max(1, phases['alone']['sps']), 2),
              'world': world, 'train': train, 'memory': memory}
    (home / FILE).write_text(json.dumps(record, indent=1) + '\n')
    return record
