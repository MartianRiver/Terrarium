# What training has cost: the hours of every run in runs/ (scratch and
# unfinished ones too) and the dollars of every rented machine in compute.toml.
# promote writes a stage's totals into its brain's entry in brains.toml, and
# the runs page shows what went into each brain, per machine (behind()).
#
#   uv run python -m terrarium.compute         # per stage, and what's been spent since the last promotion
#   uv run python -m terrarium.compute vast    # Vast's charges per instance, next to what compute.toml says

import json
import os
import sys
import time
import tomllib
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from .runs import ROOT

SESSIONS = Path(__file__).resolve().parent.parent / 'compute.toml'
BEGINNING = datetime.fromisoformat('2000-01-01T00:00:00+00:00')


def when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def read_run(run: Path) -> dict:
    return json.loads((run / 'run.json').read_text())


def metrics(run: Path) -> list[dict]:
    path = run / 'metrics.jsonl'
    text = path.read_text() if path.exists() else ''
    # a live run may be halfway through writing its last line
    return [json.loads(line) for line in text[:text.rfind('\n') + 1].splitlines()]


def seconds(run: Path) -> float:
    record = read_run(run)
    if 'finished' in record:
        return (when(record['finished']) - when(record['started'])).total_seconds()
    # stopped or still going: as far as its last update
    rows = metrics(run)
    return rows[-1]['seconds'] if rows else 0.0


def sessions(path: Path = SESSIONS) -> list[dict]:
    return tomllib.loads(path.read_text()).get('session', []) if path.exists() else []


def spent(root: Path, since: datetime, until: datetime, path: Path = SESSIONS) -> dict:
    """Runs started and rentals ended in (since, until]."""
    runs = [r for r in root.iterdir() if (r / 'run.json').exists() and since < when(read_run(r)['started']) <= until]
    rented = [s for s in sessions(path) if since < when(s['ended']) <= until]
    return {'runs': len(runs), 'hours': round(sum(map(seconds, runs)) / 3600, 2),
            'dollars': round(sum(float(s['dollars']) for s in rented), 2)}


def seconds_to(run: Path, samples: int | None) -> float:
    """How long the run took to get this far: a parent can be a checkpoint partway through."""
    rows = metrics(run)
    if samples is None or not rows or samples >= rows[-1]['samples']:
        return seconds(run)
    return next(r['seconds'] for r in rows if r['samples'] >= samples)


def maker(root: Path, parent: dict) -> Path | None:
    """The run a parent brain came out of: named in its checkpoint, or the run that ended with it."""
    named = (parent.get('meta') or {}).get('run')
    if named and (root / named / 'run.json').exists():
        return root / named
    for run in root.iterdir():
        if (run / 'run.json').exists() and read_run(run).get('brain') == parent['id']:
            return run
    return None


def line(root: Path, run: Path) -> tuple[list[tuple[Path, float]], str | None]:
    """The run and the runs behind its parent brain, newest first, each with the seconds that went into this
    brain; and the id of a parent none of them made (None when the line goes all the way back)."""
    out, parent = [(run, seconds(run))], read_run(run).get('parent')
    while parent:
        meta = parent.get('meta') or {}
        if found := maker(root, parent):
            out.append((found, seconds_to(found, meta.get('samples'))))
            parent = read_run(found).get('parent')
        elif 'run' not in meta and meta.get('parent'):
            # made from another brain without training (new actions set up, say)
            parent = {'id': meta['parent']}
        else:
            return out, parent['id']
    return out, None


def lineage_hours(root: Path, record: dict, brains: list[dict]) -> float:
    """The run that made this brain, plus the runs behind its parent, and theirs."""
    runs, missing = line(root, root / record['id'])
    hours = sum(s for _, s in runs) / 3600
    if missing:
        brain = next((b for b in brains if b['id'] == missing), None)
        if not brain:
            raise LookupError(f'the parent {missing[:12]} is neither a run in {root} nor a brain in the lineage')
        hours += brain['compute']['lineage_hours']
    return round(hours, 2)


def rented_on(record: dict, session: dict) -> bool:
    # a queue worker on a pod writes its instance in; before that, the time window and the GPU have to do
    if instance := record.get('machine', {}).get('instance'):
        return session.get('instance') == instance
    if record.get('device') != 'cuda' or not when(session['started']) <= when(record['started']) <= when(session['ended']):
        return False
    return not record.get('gpu') or session['gpu'] in record['gpu']


def hardware(record: dict, rentals: list[dict]) -> str:
    if record.get('device') == 'cuda':
        gpu = record.get('gpu') or next((s['gpu'] for s in rentals if rented_on(record, s)), 'a GPU')
        return gpu.removeprefix('NVIDIA ').removeprefix('GeForce ')
    m = record.get('machine', {})
    if 'cpu' in m:
        return f'{m["cpu"]}, {m["memory_gb"]} GB'
    return f'{m["platform"].split("-")[0]} {m["processor"]}' if m else 'not recorded'


def shares(root: Path, rentals: list[dict]) -> dict[str, float]:
    """Each rental's dollars split across the runs it hosted by their hours, idle time and all. Rentals that
    overlap with the same GPU can't be told apart, so their runs share both."""
    runs = [read_run(r) | {'seconds': seconds(r)} for r in root.iterdir() if (r / 'run.json').exists()]
    out = defaultdict(float)
    for s in rentals:
        hosted = [r for r in runs if rented_on(r, s)]
        total = sum(r['seconds'] for r in hosted)
        for r in hosted:
            out[r['id']] += float(s['dollars']) * r['seconds'] / total if total else 0
    return dict(out)


def by_hardware(rows: list[dict]) -> list[dict]:
    groups = defaultdict(lambda: {'runs': 0, 'hours': 0.0, 'dollars': 0.0})
    for r in rows:
        g = groups[r['hardware']]
        g['runs'] += 1
        g['hours'] += r['hours']
        g['dollars'] += r['dollars']
    return sorted(({'hardware': k, **v} for k, v in groups.items()), key=lambda g: -g['hours'])


def behind(root: Path, run: Path, path: Path = SESSIONS) -> dict:
    """What went into the brain this run ends with: its runs, per machine, in hours and dollars."""
    rentals = sessions(path)
    cost = shares(root, rentals)
    runs, missing = line(root, run)
    rows = []
    for r, secs in runs:
        rec, whole = read_run(r), seconds(r)
        rows.append({'id': rec['id'], 'hardware': hardware(rec, rentals), 'hours': secs / 3600,
                     'dollars': cost.get(rec['id'], 0.0) * (secs / whole if whole else 1)})
    return {'runs': rows, 'hardware': by_hardware(rows), 'hours': sum(r['hours'] for r in rows),
            'dollars': sum(r['dollars'] for r in rows), 'missing': missing}


def everything(root: Path, path: Path = SESSIONS) -> dict:
    """Every run and rental so far, dead ends and pods that never ran anything included."""
    rentals = sessions(path)
    cost = shares(root, rentals)
    records = [read_run(r) | {'seconds': seconds(r)} for r in root.iterdir() if (r / 'run.json').exists()]
    rows = [{'hardware': hardware(r, rentals), 'hours': r['seconds'] / 3600, 'dollars': cost.get(r['id'], 0.0)}
            for r in records]
    unused = [s for s in rentals if not any(rented_on(r, s) for r in records)]
    return {'hardware': by_hardware(rows), 'hours': sum(r['hours'] for r in rows),
            'unused': {'rentals': len(unused), 'dollars': sum(float(s['dollars']) for s in unused)},
            'dollars': sum(float(s['dollars']) for s in rentals)}


def totals(root: Path, record: dict, brains: list[dict], until: datetime, path: Path = SESSIONS) -> dict:
    """[brain.compute] for a brain being promoted now: this stage, and every stage up to it."""
    before = brains[-1]['compute'] if brains else {'until': BEGINNING.isoformat(), 'total_hours': 0, 'total_dollars': 0}
    stage = spent(root, when(before['until']), until, path)
    return {'until': until.isoformat(timespec='seconds'), 'lineage_hours': lineage_hours(root, record, brains),
            **stage, 'total_hours': round(before['total_hours'] + stage['hours'], 2),
            'total_dollars': round(before['total_dollars'] + stage['dollars'], 2)}


def report(brains: list[dict], root: Path = ROOT, path: Path = SESSIONS):
    for b in brains:
        c = b['compute']
        print(f'{b["stage"]}  {b["file"]}: {c["lineage_hours"]} h of training behind it; the stage took {c["runs"]} '
              f'runs, {c["hours"]} h, ${c["dollars"]:.2f}; {c["total_hours"]} h, ${c["total_dollars"]:.2f} so far'
              + (f'; like {b["like"]}' if b.get('like') else ''))
    since = when(brains[-1]['compute']['until']) if brains else BEGINNING
    now = spent(root, since, datetime.now().astimezone(), path)
    print(f'since then: {now["runs"]} runs, {now["hours"]} h, ${now["dollars"]:.2f}')


def vast_key() -> str:
    if key := os.environ.get('VAST_API_KEY'):
        return key
    env = Path(__file__).resolve().parent.parent.parent / '.env'
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith('VAST_API_KEY='):
            return line.split('=', 1)[1].strip()
    raise SystemExit('no VAST_API_KEY in the environment or .env')


def vast_charges(days: int = 90) -> dict[int, float]:
    """Dollars per instance over the last `days`, as Vast bills them (GPU, disk and bandwidth)."""
    end = int(time.time())
    query = {'select_filters': {'day': {'gte': end - days * 86400, 'lte': end}}, 'limit': 100, 'format': 'table'}
    charges, token = defaultdict(float), None
    while True:
        args = query | ({'after_token': token} if token else {})
        url = 'https://console.vast.ai/api/v0/charges/?' + '&'.join(
            f'{k}={quote_plus(json.dumps(v))}' for k, v in args.items())
        request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + vast_key()})
        with urllib.request.urlopen(request, timeout=60) as r:
            page = json.loads(r.read())
        for row in page['results']:
            if row['type'] == 'instance':
                charges[int(row['source'].removeprefix('instance-'))] += row['amount']
        if not (token := page.get('next_token')):
            return dict(charges)


def check_vast(path: Path = SESSIONS):
    recorded = {s['instance']: s['dollars'] for s in sessions(path) if s['provider'] == 'vast'}
    for instance, dollars in sorted(vast_charges().items()):
        note = recorded.get(instance)
        state = 'missing from compute.toml' if note is None else 'ok' if abs(note - dollars) < 0.005 else f'compute.toml says {note}'
        print(f'instance {instance}: ${dollars:.3f}  {state}')


def main():
    from .promote import lineage
    if sys.argv[1:] == ['vast']:
        check_vast()
    elif not sys.argv[1:]:
        report(lineage())
    else:
        raise SystemExit('usage: python -m terrarium.compute [vast]')


if __name__ == '__main__':
    main()
