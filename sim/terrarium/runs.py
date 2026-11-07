# Run records: every training run gets a folder under runs/ (not in git) that
# says exactly what made it: commit, both configs, parent brain, schema, seed,
# machine and versions. A run from uncommitted code is only allowed as scratch;
# it keeps the diff so it can be understood, and can never be promoted.

import json
import os
import platform
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

from .log import Logger

log = Logger('runs')

ROOT = Path(__file__).resolve().parent.parent.parent / 'runs'


class GitError(RuntimeError):
    pass


def git(*args) -> str:
    """git's output, or GitError: a run whose code can't be named mustn't pass for a clean one."""
    out = subprocess.run(['git', *args], capture_output=True, text=True, cwd=Path(__file__).parent)
    if out.returncode:
        why = out.stderr.strip()
        if 'dubious ownership' in why:
            why += "\n(a tree copied in from another user, as on a pod: git config --global --add safe.directory '*')"
        raise GitError(f'git {" ".join(args)} failed: {why}')
    return out.stdout.strip()


def dirty() -> bool:
    # untracked files count too, so a new module isn't missed
    return bool(git('status', '--porcelain'))


def cpu() -> str:
    if sys.platform == 'darwin':
        return subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True, text=True).stdout.strip()
    if sys.platform == 'win32':
        import winreg
        # platform.processor() there is only the family and model numbers
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            return winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    info = Path('/proc/cpuinfo')
    names = [line.split(':', 1)[1].strip() for line in info.read_text().splitlines() if line.startswith('model name')] \
        if info.exists() else []
    return names[0] if names else platform.processor() or platform.machine()


def cpu_quota(cgroup: Path = Path('/sys/fs/cgroup')) -> int | None:
    """CPUs a container is allowed. torch and os count the host's cores, which can be eight times as many."""
    try:
        if (cgroup / 'cpu.max').exists():
            quota, period = (cgroup / 'cpu.max').read_text().split()
        else:
            # cgroup v1, still on some Vast hosts; -1 is no limit
            quota, period = ((cgroup / 'cpu' / f'cpu.cfs_{k}_us').read_text().strip() for k in ('quota', 'period'))
        return None if quota in ('max', '-1') else max(1, int(quota) // int(period))
    except (OSError, ValueError):
        return None


def rental(environ: Path = Path('/proc/1/environ')) -> dict:
    """Which rented pod this is, so samples a dollar can be told apart by host: Vast and RunPod set it in the
    container's first process, which an ssh session doesn't inherit."""
    env = dict(os.environ)
    try:
        env |= dict(e.split('=', 1) for e in environ.read_bytes().decode(errors='replace').split('\0') if '=' in e)
    except OSError:
        pass
    # Vast gives every instance its own CONTAINER_API_KEY (never recorded); its id is the instance's
    if 'CONTAINER_ID' in env and 'CONTAINER_API_KEY' in env:
        return {'provider': 'vast', 'instance': env.get('CONTAINER_ID')}
    if 'RUNPOD_POD_ID' in env:
        return {'provider': 'runpod', 'instance': env['RUNPOD_POD_ID']}
    return {}


def memory_gb() -> int:
    # here, not at the top: the coordinator imports this module and runs on a bare python
    import psutil
    return round(psutil.virtual_memory().total / 2**30)


def commit() -> str:
    """For replay headers, which can be recorded outside a checkout."""
    try:
        return git('rev-parse', '--short', 'HEAD') + ('-dirty' if dirty() else '')
    except GitError:
        return 'unknown'


class DirtyTree(RuntimeError):
    pass


class Run:
    def __init__(self, name: str, record: dict, scratch: bool = False, root: Path = ROOT):
        """Make the folder and write run.json. record is whatever the caller adds: configs, parent, seed."""
        if dirty() and not scratch:
            raise DirtyTree('there are uncommitted changes; commit them, or pass --scratch for a run that '
                            'can never be promoted')
        self.id = time.strftime('%Y%m%d-%H%M%S') + f'-{name}'
        self.dir = root / self.id
        (self.dir / 'checkpoints').mkdir(parents=True)
        is_dirty = dirty()
        if is_dirty:
            (self.dir / 'diff.patch').write_text(git('diff', 'HEAD') + '\n')
            (self.dir / 'untracked.txt').write_text(git('ls-files', '--others', '--exclude-standard') + '\n')
        self.record = {
            'id': self.id, 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'commit': git('rev-parse', 'HEAD'), 'dirty': is_dirty, 'scratch': scratch,
            'machine': {'platform': platform.platform(), 'processor': platform.processor() or platform.machine(),
                        'cpu': cpu(), 'memory_gb': memory_gb(), **rental()},
            'versions': {'python': sys.version.split()[0],
                         **{p: version(p) for p in ('numpy', 'pymunk', 'torch')}},
            **record,
        }
        self.save()
        self.metrics = open(self.dir / 'metrics.jsonl', 'a')
        log.info('run started', id=self.id, commit=self.record['commit'][:7], dirty=is_dirty, scratch=scratch)

    def save(self):
        (self.dir / 'run.json').write_text(json.dumps(self.record, indent=2) + '\n')

    def log_metrics(self, row: dict):
        self.metrics.write(json.dumps(row) + '\n')
        self.metrics.flush()

    def finish(self, **result):
        self.record |= {'finished': time.strftime('%Y-%m-%dT%H:%M:%S%z'), **result}
        self.save()
        self.metrics.close()
        log.info('run finished', id=self.id, **result)
