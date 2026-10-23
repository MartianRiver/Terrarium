# Promote a finished run's last checkpoint to be a stage's brain: it has to come
# from committed code that's on next and clearly beat random on the evals. The
# weights are copied to a backups folder outside the repo and the brain gets an
# entry in the lineage file, brains.toml, with what the stage's training cost
# (compute.py): every run next to it in runs/ since the last promotion.
#
#   uv run python -m terrarium.promote runs/<run> --stage 0.2 --backups DIR [--like "..."]

import argparse
import json
import shutil
import subprocess
import time
import tomllib
from datetime import datetime
from pathlib import Path

from . import compute, evals
from .brain import brain_id, load
from .log import Logger
from .schema import SchemaError

log = Logger('promote')

LINEAGE = Path(__file__).resolve().parent.parent / 'brains.toml'


class Refused(RuntimeError):
    pass


def lineage(path: Path = LINEAGE) -> list[dict]:
    return tomllib.loads(path.read_text()).get('brain', []) if path.exists() else []


def on_branch(commit: str, branch: str) -> bool:
    return subprocess.run(['git', 'merge-base', '--is-ancestor', commit, branch], capture_output=True,
                          cwd=Path(__file__).parent).returncode == 0


def check(run_dir: Path, stage: str, path: Path, branch: str) -> tuple[dict, dict, Path]:
    record = json.loads((run_dir / 'run.json').read_text())
    run = record['id']
    if 'finished' not in record:
        raise Refused(f'{run} never finished')
    if record['scratch'] or record['dirty']:
        raise Refused(f'{run} is a scratch run; train again from {branch} with nothing uncommitted')
    # a squash merge leaves a branch's commits out of next, so this also catches runs from feature branches
    if not on_branch(record['commit'], branch):
        raise Refused(f'{run} ran from {record["commit"][:7]}, which isn\'t on {branch}; '
                      f'train again from {branch} once the code is merged')
    checkpoint = run_dir / 'checkpoints' / record['checkpoint']
    if brain_id(checkpoint) != record['brain']:
        raise Refused(f'{checkpoint.name} has changed since {run} finished')
    try:
        load(checkpoint)
    except SchemaError as e:
        raise Refused(str(e))
    scores = json.loads((run_dir / 'evals.json').read_text())
    if scores['checkpoint'] != checkpoint.name:
        raise Refused(f'evals.json scores {scores["checkpoint"]}, not {checkpoint.name}')
    if failed := evals.beats(scores['brain'], scores['random']):
        raise Refused(f'{checkpoint.name} doesn\'t clearly beat random: ' + '; '.join(failed))
    if any(b['stage'] == stage for b in lineage(path)):
        raise Refused(f'stage {stage} already has a brain in {path.name}; take its entry out to replace it')
    return record, scores, checkpoint


def numbers(score: dict) -> dict:
    f, s = score['food_per_minute'], score['seconds_alive']
    return {'food_per_minute': round(f['mean'], 3), 'food_per_minute_stderr': round(f['stderr'], 3),
            'seconds_alive': round(s['mean'], 1), 'seconds_alive_stderr': round(s['stderr'], 1)}


def tables(name: str, entry: dict) -> list[str]:
    # json writes strings, numbers and lists of strings the way TOML reads them
    head = f'[[{name}]]' if '.' not in name else f'[{name}]'
    lines = ['', head, *(f'{k} = {json.dumps(v)}' for k, v in entry.items() if not isinstance(v, dict))]
    for k, v in entry.items():
        if isinstance(v, dict):
            lines += tables(f'{name}.{k}', v)
    return lines


def promote(run_dir: Path | str, stage: str, backups: Path | str, path: Path = LINEAGE,
            branch: str = 'next', like: str = '', sessions: Path = compute.SESSIONS) -> dict:
    run_dir = Path(run_dir)
    record, scores, checkpoint = check(run_dir, stage, path, branch)
    try:
        cost = compute.totals(run_dir.parent, record, lineage(path), datetime.now().astimezone(), sessions)
    except LookupError as e:
        raise Refused(str(e))
    sha = record['brain']
    file = f'{sha[:12]}.pt'
    copy = Path(backups) / 'brains' / file
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(checkpoint, copy)
    if brain_id(copy) != sha:
        raise Refused(f'the copy at {copy} doesn\'t match {checkpoint}')

    entry = {
        'stage': stage, 'id': sha, 'file': file, 'parent': (record['parent'] or {}).get('id', ''),
        'commit': record['commit'], 'run': record['id'], 'samples': record['samples'],
        'schema': record['schema']['version'], 'promoted': time.strftime('%Y-%m-%d'), 'release': f'v{stage}.0',
        **({'like': like} if like else {}),
        'evals': {'config': record['world']['file'], 'seed': scores['brain']['seed'],
                  'episodes': scores['brain']['episodes'],
                  'brain': numbers(scores['brain']), 'random': numbers(scores['random'])},
        'compute': cost,
    }
    with open(path, 'a') as f:
        f.write('\n'.join(tables('brain', entry)) + '\n')
    log.info('promoted', stage=stage, brain=file, run=record['id'], backup=str(copy))
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', help='the run folder, runs/<date>-<time>-<name>')
    parser.add_argument('--stage', required=True, help='e.g. 0.2')
    parser.add_argument('--backups', required=True, help='a folder outside the repo; the weights go in its brains/')
    parser.add_argument('--like', default='', help='the animal its brain is sort of on the level of (docs/brain.md)')
    args = parser.parse_args()
    try:
        promote(args.run, args.stage, args.backups, like=args.like)
    except Refused as e:
        raise SystemExit(f'not promoted: {e}')


if __name__ == '__main__':
    main()
