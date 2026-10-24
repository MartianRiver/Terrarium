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


def git(*args) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()


def dirty() -> bool:
    # untracked files count too, so a new module isn't missed
    return bool(git('status', '--porcelain'))


def cpu() -> str:
    if sys.platform == 'darwin':
        return subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True, text=True).stdout.strip()
    info = Path('/proc/cpuinfo')
    names = [line.split(':', 1)[1].strip() for line in info.read_text().splitlines() if line.startswith('model name')] \
        if info.exists() else []
    return names[0] if names else platform.processor() or platform.machine()


def memory_gb() -> int:
    return round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30)


def commit() -> str:
    return (git('rev-parse', '--short', 'HEAD') or 'unknown') + ('-dirty' if dirty() else '')


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
                        'cpu': cpu(), 'memory_gb': memory_gb()},
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
