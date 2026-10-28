# The public board: what each machine has done for the queue, for the site's
# Terrarium at Home page. Only totals and what the machine is. No hostnames or
# addresses, no job progress, and nothing about what its owner is doing right
# now (a lent machine "waiting" says someone is at it), so last active is a day.
# Workers report themselves; what they send is cut down to known fields here
# before it's kept or shown. What my machines and rented GPUs trained outside the
# queue comes from board.toml, written from the ledger (compute.py).

import time
import tomllib
from pathlib import Path

# trusted machines are River's own
KINDS = {'trusted': 'mine', 'rented': 'rented', 'donor': 'lent'}
INFO = {'platform': str, 'slots': int, 'trusted': bool, 'version': int, 'state': str, 'reason': str}
TEXT = 120
USAGE = ['samples_per_second', 'collect_seconds', 'update_seconds',
         *(f'{k}_{p}' for k in ('gpu_busy', 'gpu_gb', 'gpu_power', 'cpu_cores', 'machine_cpu') for p in ('collect', 'update'))]
OUTSIDE = Path(__file__).resolve().parent.parent / 'board.toml'


def text(value) -> str | None:
    return value[:TEXT] if isinstance(value, str) else None


def number(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1_000_000 else None


def reading(value) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 10_000_000
    return round(float(value), 3) if ok else None


def clean(info: dict) -> dict:
    """A worker's report, kept to the fields the coordinator knows, strings cut short."""
    out = {}
    for key, kind in INFO.items():
        value = info.get(key)
        if kind is bool and isinstance(value, bool):
            out[key] = value
        elif kind is int and number(value) is not None:
            out[key] = value
        elif kind is str and text(value) is not None:
            out[key] = text(value)
    specs = info.get('specs')
    if isinstance(specs, dict):
        gpus = specs.get('gpus')
        gpus = gpus if isinstance(gpus, list) else []
        out['specs'] = {'os': text(specs.get('os')), 'cpu': text(specs.get('cpu')),
                        'cores': number(specs.get('cores')), 'memory_gb': number(specs.get('memory_gb')),
                        'gpus': [{'name': text(g.get('name')), 'memory_gb': number(g.get('memory_gb'))}
                                 for g in gpus[:8] if isinstance(g, dict)]}
    # how hard it trains lately (terrarium.usage), for the admin page only: summary() never shows it
    if isinstance(got := info.get('usage'), dict):
        kept: dict[str, float | str] = {k: v for k in USAGE if (v := reading(got.get(k))) is not None}
        if isinstance(held := got.get('held_back'), str):
            kept['held_back'] = held[:300]
        out['usage'] = kept
    return out


def work(jobs: list[dict]) -> dict[str, dict]:
    """Samples, hours and jobs done per machine. Hours run from its last claim of each job to the
    upload, so a checkout's first setup counts; a job handed back counts nothing."""
    done: dict[str, dict] = {}
    for job in jobs:
        if job['state'] != 'done':
            continue
        name = job['worker']
        claimed = [t for t, what in job['history'] if what == f'claimed by {name}']
        finished = [t for t, what in job['history'] if what == f'done by {name}']
        d = done.setdefault(name, {'samples': 0, 'seconds': 0.0, 'jobs': 0, 'last': 0.0})
        d['samples'] += job['spec']['samples']
        d['jobs'] += 1
        if claimed and finished:
            d['seconds'] += max(0.0, finished[-1] - claimed[-1])
            d['last'] = max(d['last'], finished[-1])
    return done


def outside(path: Path | None = None) -> list[dict]:
    path = path or OUTSIDE
    return tomllib.loads(path.read_text()).get('machine', []) if path.exists() else []


def kind_of(role: str | None) -> str | None:
    return KINDS.get(role or '')


def summary(jobs: list[dict], workers: dict[str, dict], roles: dict[str, str], now: float | None = None,
            ledger: list[dict] | None = None) -> dict:
    now = now or time.time()
    done = work(jobs)
    machines = []
    off = {m['name']: m for m in ledger or []}
    for name in sorted(set(workers) | set(done)):
        seen = workers.get(name, {})
        kind = kind_of(seen.get('role') or roles.get(name))
        if kind is None:
            continue
        specs = (seen.get('info') or {}).get('specs') or {}
        gpus = [g['name'] for g in specs.get('gpus') or [] if g.get('name')]
        d = done.get(name, {'samples': 0, 'seconds': 0.0, 'jobs': 0, 'last': 0.0})
        last = max(seen.get('seen', 0.0), d['last'])
        machines.append({'name': name, 'kind': kind, 'gpu': gpus[0] if gpus else specs.get('cpu'),
                         'samples': d['samples'], 'hours': round(d['seconds'] / 3600, 2), 'jobs': d['jobs'],
                         'last_active': time.strftime('%Y-%m-%d', time.gmtime(last)) if last else None})
    for m in machines:
        if o := off.pop(m['name'], None):
            m['samples'] += o['samples']
            m['hours'] = round(m['hours'] + o['hours'], 2)
            m['jobs'] += o['runs']
            m['gpu'] = m['gpu'] or o['gpu']
            m['last_active'] = max(filter(None, (m['last_active'], o['last_active'])))
    machines += [{'name': o['name'], 'kind': o['kind'], 'gpu': o['gpu'], 'samples': o['samples'], 'hours': o['hours'],
                  'jobs': o['runs'], 'last_active': o['last_active']} for o in off.values()]
    machines.sort(key=lambda m: -m['samples'])
    totals = {}
    for kind in KINDS.values():
        mine = [m for m in machines if m['kind'] == kind]
        totals[kind] = {'machines': len(mine), 'samples': sum(m['samples'] for m in mine),
                        'hours': round(sum(m['hours'] for m in mine), 2)}
    return {'at': round(now), 'machines': machines, 'totals': totals}
