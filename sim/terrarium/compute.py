# What training has cost: the hours of every run in runs/ (scratch and
# unfinished ones too) and the dollars of every rented machine in compute.toml.
# promote writes a stage's totals into its brain's entry in brains.toml, and
# the runs page shows what went into each brain, per machine (behind()).
#
#   uv run python -m terrarium.compute         # per stage, and what's been spent since the last promotion
#   uv run python -m terrarium.compute vast    # Vast's charges per instance, next to what compute.toml says
#   uv run python -m terrarium.compute board   # board.toml: what trained outside the queue, for the public board

import json
import os
import re
import sys
import time
import tomllib
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from .runs import ROOT

SESSIONS = Path(__file__).resolve().parent.parent / 'compute.toml'
BEGINNING = datetime.fromisoformat('2000-01-01T00:00:00+00:00')
# the queue on Atlas took its first job this day; queue runs from before were tests on a queue on the Mac
QUEUE_OPENED = datetime.fromisoformat('2026-10-26T00:00:00+11:00')
BOARD = SESSIONS.parent / 'board.toml'


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
    # time a lent machine's worker held the job paused while its owner used it
    paused = record.get('paused', 0)
    if 'finished' in record:
        return (when(record['finished']) - when(record['started'])).total_seconds() - paused
    # stopped or still going: as far as its last update
    rows = metrics(run)
    return rows[-1]['seconds'] - paused if rows else 0.0


def sessions(path: Path = SESSIONS) -> list[dict]:
    return tomllib.loads(path.read_text()).get('session', []) if path.exists() else []


def machines(path: Path = SESSIONS) -> list[dict]:
    """My own machines, by the cpu and memory a run records, with the name to show them by."""
    return tomllib.loads(path.read_text()).get('machine', []) if path.exists() else []


def rented_hours(session: dict) -> float:
    # the whole rental, setup and idle included, not just the training on it
    return (when(session['ended']) - when(session['started'])).total_seconds() / 3600


def spent(root: Path, since: datetime, until: datetime, path: Path = SESSIONS) -> dict:
    """Runs started and rentals ended in (since, until]."""
    runs = [r for r in root.iterdir() if (r / 'run.json').exists() and since < when(read_run(r)['started']) <= until]
    rented = [s for s in sessions(path) if since < when(s['ended']) <= until]
    return {'runs': len(runs), 'hours': round(sum(map(seconds, runs)) / 3600, 2),
            'rented_hours': round(sum(map(rented_hours, rented)), 2),
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
    if record.get('gpu') and session['gpu'] not in record['gpu']:
        return False
    # "Xeon Gold 6138, 40 cores" matches "Intel(R) Xeon(R) Gold 6138 CPU @ 2.00GHz"
    cpu = record.get('machine', {}).get('cpu')
    return not (cpu and 'cpu' in session) or all(w in cpu for w in session['cpu'].split(',')[0].split())


def cpu_name(cpu: str) -> str:
    """"Intel(R) Xeon(R) Gold 6154 CPU @ 3.00GHz" -> "Xeon Gold 6154", "AMD EPYC 7662 64-Core Processor" -> "EPYC 7662"."""
    cpu = re.sub(r'\((R|TM)\)|@.*$|\bCPU\b|\bProcessor\b|\b\d+-Core\b|^(Intel|AMD)\b', '', cpu)
    return ' '.join(cpu.split())


def hardware(record: dict, rentals: list[dict], mine: list[dict] | None = None) -> str:
    m = record.get('machine', {})
    if record.get('device') == 'cuda':
        rental = next((s for s in rentals if rented_on(record, s)), {})
        gpu = (record.get('gpu') or rental.get('gpu') or 'a GPU').removeprefix('NVIDIA ').removeprefix('GeForce ')
        # the rental knows the cores it came with; older runs at least recorded the CPU's model
        cpu = rental.get('cpu') or (cpu_name(m['cpu']) if 'cpu' in m else None)
        return f'{gpu}, {cpu}' if cpu else gpu
    if 'cpu' in m:
        named = next((k['name'] for k in mine or [] if k.get('cpu') == m['cpu'] and k.get('memory_gb') == m['memory_gb']), None)
        return named or f'{m["cpu"]}, {m["memory_gb"]} GB'
    # runs from before cpu and memory were recorded: a machine of mine can be named by its platform
    named = next((k['name'] for k in mine or [] if 'platform' in k and m.get('platform', '').startswith(k['platform'])), None)
    if named:
        return named
    return f'{m["platform"].split("-")[0]} {m["processor"]}' if m else 'not recorded'


def shares(root: Path, rentals: list[dict]) -> dict[str, tuple[float, float]]:
    """Each rental's dollars and hours split across the runs it hosted by their hours, idle time and all. Rentals
    that overlap with the same GPU can't be told apart, so their runs share both."""
    runs = [read_run(r) | {'seconds': seconds(r)} for r in root.iterdir() if (r / 'run.json').exists()]
    out = defaultdict(lambda: (0.0, 0.0))
    for s in rentals:
        hosted = [r for r in runs if rented_on(r, s)]
        total = sum(r['seconds'] for r in hosted)
        for r in hosted:
            share = r['seconds'] / total if total else 0
            dollars, hours = out[r['id']]
            out[r['id']] = (dollars + float(s['dollars']) * share, hours + rented_hours(s) * share)
    return dict(out)


def by_hardware(rows: list[dict]) -> list[dict]:
    groups = defaultdict(lambda: {'runs': 0, 'hours': 0.0, 'rented_hours': 0.0, 'dollars': 0.0})
    for r in rows:
        g = groups[r['hardware']]
        g['runs'] += 1
        for k in ('hours', 'rented_hours', 'dollars'):
            g[k] += r[k]
    return sorted(({'hardware': k, **v} for k, v in groups.items()), key=lambda g: -g['hours'])


def behind(root: Path, run: Path, path: Path = SESSIONS) -> dict:
    """What went into the brain this run ends with: its runs, per machine, in hours (training, and rented with idle
    time) and dollars."""
    rentals, mine = sessions(path), machines(path)
    cost = shares(root, rentals)
    runs, missing = line(root, run)
    rows = []
    for r, secs in runs:
        rec, whole = read_run(r), seconds(r)
        part = secs / whole if whole else 1
        dollars, rented = cost.get(rec['id'], (0.0, 0.0))
        rows.append({'id': rec['id'], 'hardware': hardware(rec, rentals, mine), 'hours': secs / 3600,
                     'rented_hours': rented * part, 'dollars': dollars * part})
    return {'runs': rows, 'hardware': by_hardware(rows), 'hours': sum(r['hours'] for r in rows),
            'rented_hours': sum(r['rented_hours'] for r in rows), 'dollars': sum(r['dollars'] for r in rows),
            'missing': missing}


def everything(root: Path, path: Path = SESSIONS) -> dict:
    """Every run and rental so far, dead ends included, and rentals with no training run on them (evals, probes,
    failed starts)."""
    rentals, mine = sessions(path), machines(path)
    cost = shares(root, rentals)
    records = [read_run(r) | {'seconds': seconds(r)} for r in root.iterdir() if (r / 'run.json').exists()]
    rows = [{'hardware': hardware(r, rentals, mine), 'hours': r['seconds'] / 3600,
             'dollars': cost.get(r['id'], (0.0, 0.0))[0], 'rented_hours': cost.get(r['id'], (0.0, 0.0))[1]}
            for r in records]
    unused = [s for s in rentals if not any(rented_on(r, s) for r in records)]
    return {'hardware': by_hardware(rows), 'hours': sum(r['hours'] for r in rows),
            'unused': {'rentals': len(unused), 'rented_hours': sum(map(rented_hours, unused)),
                       'dollars': sum(float(s['dollars']) for s in unused)},
            'rented_hours': sum(map(rented_hours, rentals)), 'dollars': sum(float(s['dollars']) for s in rentals)}


def on_board(record: dict, rentals: list[dict], mine: list[dict], sizes: dict[str, int]) -> tuple[str, str, str] | None:
    """The board's name, kind and GPU for a run on one of my machines (one with a handle) or a rented GPU."""
    if record.get('device') == 'cuda':
        rental = next((s for s in rentals if rented_on(record, s)), {})
        gpu = (record.get('gpu') or rental.get('gpu') or '').removeprefix('NVIDIA ').removeprefix('GeForce ')
        if not gpu:
            return None
        memory = rental.get('gpu_memory_gb') or sizes.get(gpu)
        gpu = f'{gpu} {memory} GB' if memory else gpu
        return f'rented {gpu}', 'rented', gpu
    named = hardware(record, rentals, mine)
    own = next((k for k in mine if k['name'] == named and 'handle' in k), None)
    return (own['handle'], 'mine', own['cpu']) if own else None


def board(root: Path = ROOT, path: Path = SESSIONS) -> list[dict]:
    """What my machines and rented GPUs trained outside the queue, per board name. Runs that came through the
    queue on Atlas are counted there already."""
    rentals, mine = sessions(path), machines(path)
    sizes = tomllib.loads(path.read_text()).get('gpu_memory', {}) if path.exists() else {}
    rows: dict[str, dict] = {}
    for r in sorted(root.iterdir()):
        if not (r / 'run.json').exists():
            continue
        record = read_run(r)
        if (r / 'job.json').exists() and when(record['started']) >= QUEUE_OPENED:
            continue
        who = on_board(record, rentals, mine, sizes)
        if not who:
            continue
        name, kind, gpu = who
        secs, done = seconds(r), metrics(r)
        row = rows.setdefault(name, {'name': name, 'kind': kind, 'gpu': gpu, 'samples': 0, 'hours': 0.0, 'runs': 0,
                                     'last_active': ''})
        row['samples'] += done[-1]['samples'] if done else 0
        row['hours'] += secs / 3600
        row['runs'] += 1
        ended = (when(record['started']) + timedelta(seconds=secs)).astimezone(timezone.utc).date().isoformat()
        row['last_active'] = max(row['last_active'], ended)
    return sorted(({**r, 'hours': round(r['hours'], 2)} for r in rows.values()), key=lambda r: -r['samples'])


def write_board(rows: list[dict], out: Path):
    lines = ['# What my machines and rented GPUs trained outside the queue, from runs/ and compute.toml',
             '# (`python -m terrarium.compute board`). The board adds it to what the queue counts; runs count as jobs.']
    for r in rows:
        lines += ['', '[[machine]]'] + [f'{k} = {json.dumps(v)}' for k, v in r.items()]
    out.write_text('\n'.join(lines) + '\n')


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
              f'runs, {c["hours"]} h of training, {c.get("rented_hours", 0)} h rented, ${c["dollars"]:.2f}; {c["total_hours"]} h, ${c["total_dollars"]:.2f} so far'
              + (f'; like {b["like"]}' if b.get('like') else ''))
    since = when(brains[-1]['compute']['until']) if brains else BEGINNING
    now = spent(root, since, datetime.now().astimezone(), path)
    print(f'since then: {now["runs"]} runs, {now["hours"]} h of training, {now["rented_hours"]} h rented, '
          f'${now["dollars"]:.2f}')


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
    elif sys.argv[1:] == ['board']:
        write_board(board(), BOARD)
        print(BOARD.read_text())
    elif not sys.argv[1:]:
        report(lineage())
    else:
        raise SystemExit('usage: python -m terrarium.compute [vast|board]')


if __name__ == '__main__':
    main()
