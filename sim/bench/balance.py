# The balance test for long worlds: scripted colonies live in a world with no end for several day-night cycles, and
# we watch whether it holds a population. A long world must do that before any brain lives in it.
#
#   uv run python bench/balance.py bench/worlds/ab-2x9.toml --policy nester forager --supply 1.5 0.8 --seeds 4 --cycles 2 --out /tmp/bal
#   uv run python bench/balance_report.py /tmp/bal          (the HTML report; one balance.json per run in the folder)
#
# A run is one world x one policy x one setting, with `--seeds` games side by side in one World (seed i is arena i of
# `--seed`, so game i is the same game whatever the number of seeds). The games never reset: dead stay dead, births
# fill the empty places, and the clock runs on after a colony is gone. Nothing in the sim had to change for that, since
# World only reports `ended` and leaves starting over to the caller; [episode] seconds is set past the last tick.
# Series are sampled every `--every` seconds of world time.

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '1')

import numpy as np

import balance_supply as supply
from balance_forager import forager_policy
from terrarium import World, load
from terrarium.config import Config, Episode
from terrarium.evals import POLICIES
from terrarium.log import Logger

SEED = 5_000_000
POLICY = {'carrier': POLICIES['carrier'], 'nester': POLICIES['nester'], 'forager': forager_policy}
# where a nim was when it died, by when and by place
WHERE = ('day_out', 'day_home', 'night_out', 'night_home')
log = Logger('balance')


def adjust(cfg: Config, a: argparse.Namespace) -> Config:
    f, g = cfg.food, cfg.grass
    if a.food_count is not None:
        f = replace(f, count=a.food_count)
    if a.regrow:
        f = replace(f, regrow_min=a.regrow[0], regrow_max=a.regrow[1])
    if a.patches is not None:
        f = replace(f, patches=a.patches, middle=min(f.middle, a.patches))
    if a.patch_radius is not None:
        f = replace(f, patch_radius=a.patch_radius)
    if a.grass:
        meadows, radius, distance, regrow = a.grass
        g = replace(g, meadows=int(meadows), radius=radius, distance=distance, regrow=regrow, bite=0.25, food=0.4)
    return replace(cfg, food=f, grass=g)


class Recorder:
    """Series sampled every few seconds and deaths counted every tick, per game."""

    def __init__(self, world: World):
        self.w = world
        a, c = world.arenas, len(world.nests)
        self.t: list[float] = []
        self.series = {k: [] for k in ('alive', 'store', 'births', 'deaths', 'picks', 'food', 'grass', 'carried', 'dark', 'eggs')}
        self.died = np.zeros((a, len(WHERE)), int)
        # of those, dying in a nest whose store held jelly
        self.beside_store = np.zeros(a, int)
        self.colony_deaths = np.zeros((a, c), int)
        self.emptied = np.full((a, c), -1.0)

    def sample(self):
        w = self.w
        c = np.arange(len(w.nests))
        self.t.append(w.tick * w.cfg.dt)
        s = self.series
        s['alive'].append(np.stack([(w.alive & (w.colony == k)).sum(1) for k in c], 1))
        s['store'].append(w.store.copy())
        s['births'].append(w.hatched.copy())
        s['deaths'].append(self.colony_deaths.copy())
        s['picks'].append(w.meals.sum(1))
        s['food'].append(w.food_present[:, :w.wild].sum(1))
        s['grass'].append(w.grass.cover.sum((1, 2)) / np.maximum(w.grass.start.sum((1, 2)), 1e-9) if w.grass else np.zeros(w.arenas))
        s['carried'].append((w.crop * w.alive).sum(1))
        s['dark'].append(w.dark.copy())
        s['eggs'].append((w.egg > 0).sum(1))

    def watch(self, before: dict):
        """After a step: who died this tick, by where they stood and whether it was dark, from the state before it."""
        w = self.w
        gone = before['alive'] & ~w.alive
        if not gone.any():
            return
        for k in np.unique(w.colony[np.nonzero(gone)[1]]):
            self.colony_deaths[:, k] += (gone & (w.colony == k)).sum(1)
        place = before['dark'][:, None] * 2 + before['home']
        for j in range(len(WHERE)):
            self.died[:, j] += (gone & (place == j)).sum(1)
        self.beside_store += (gone & before['home'] & before['stocked']).sum(1)
        left = ~np.stack([w.alive[:, w.colony == k].any(1) for k in range(len(w.nests))], 1) & (self.emptied < 0)
        self.emptied[left] = w.tick * w.cfg.dt


def simulate(cfg: Config, policy: str, seeds: int, cycles: float, every: float, seed: int) -> dict:
    """One run to the end of its cycles: the series, the death counts and how fast it went."""
    cfg = replace(cfg, episode=Episode(seconds=(cycles + 1) * supply.cycle_length(cfg)))
    world = World(cfg, seeds, seed)
    act = POLICY[policy](world)
    rec = Recorder(world)
    ticks = round(cycles * supply.cycle_length(cfg) * cfg.tick_hz)
    step = max(1, round(every * cfg.tick_hz))
    start = time.perf_counter()
    for tick in range(ticks + 1):
        if tick % step == 0:
            rec.sample()
        if tick == ticks:
            break
        home = world.nest_at() == world.colony
        before = {'alive': world.alive.copy(), 'dark': world.dark.copy(), 'home': home,
                  'stocked': np.take_along_axis(world.store, np.broadcast_to(world.colony, home.shape), 1) > 0}
        world.step(act(world))
        rec.watch(before)
    wall = time.perf_counter() - start
    return {'t': rec.t, **{k: np.array(v).tolist() for k, v in rec.series.items()},
            'deaths_by': dict(zip(WHERE, rec.died.sum(0).tolist())), 'deaths_by_game': rec.died.tolist(),
            'beside_store': rec.beside_store.tolist(), 'emptied': rec.emptied.tolist(),
            'wall': wall, 'world_seconds': ticks * cfg.dt, 'speed': ticks * cfg.dt / wall}


# a run shorter than this many days can't show a world holds: the ROADMAP asks for a few days of world time
MIN_CYCLES = 4


def gates(run: dict, start: int, kind: str, cycle: float) -> dict:
    """The proposed gates (bigworld review) from a run's series: per game, then over games. kind: rich, lean or none.
    The series keep every colony apart, so a colony dying out in a game the other colony carries still shows; a run
    shorter than MIN_CYCLES days is 'incomplete', not a pass."""
    alive = np.array(run['alive'])                                         # samples, games, colonies
    pop = alive.sum(-1)                                                    # samples, games
    t = np.array(run['t'])
    n = pop.shape[1]
    at = lambda s: pop[min(np.searchsorted(t, s - 1e-6), len(t) - 1)]      # pop at the sample at or after time s
    end, day2 = at(t[-1]), at(2 * cycle)
    died_out = (pop.min(0) == 0)
    colony_out = (alive.min(0) == 0)                                       # games, colonies
    cycles = t[-1] / cycle
    days = [float(np.median(at(d * cycle))) for d in range(1, int(cycles + 1e-9) + 1)]
    out = {'games': n, 'colonies': alive.shape[2], 'start': start, 'end_median': float(np.median(end)), 'end_share': float(np.median(end) / start),
           'day2_share': float(np.median(day2) / start), 'peak_median': float(np.median(pop.max(0))),
           'extinct_games': int(died_out.sum()), 'extinct_share': float(died_out.mean()),
           'extinct_colonies': int(colony_out.sum()), 'colony_extinct_share': float(colony_out.mean()),
           'daily_median': days, 'lowest_median': float(np.median(pop.min(0))), 'kind': kind, 'cycles': cycles}
    # a late decline: nims a cycle lost between the middle of the run and its end, median of games; needs 4+ cycles
    if cycles >= 4:
        mid = np.median(at(t[-1] / 2))
        out['late_slope'] = float((np.median(end) - mid) / (cycles / 2))
    checks = {}
    if kind == 'rich':
        checks = {'keeps 90% of the start': out['end_share'] >= 0.9,
                  'keeps 90% of the start every day': bool(days) and min(days) >= 0.9 * start,
                  'no game goes extinct': out['extinct_games'] == 0,
                  'no colony goes extinct': out['extinct_colonies'] == 0}
    elif kind == 'lean':
        checks = {'ends at 50-80% of the start': 0.5 <= out['end_share'] <= 0.8,
                  'keeps 50% through day two': out['day2_share'] >= 0.5,
                  'extinct in under 10% of games': out['extinct_share'] < 0.1,
                  'a colony extinct in under 10% of its games': out['colony_extinct_share'] < 0.1}
    if checks and 'late_slope' in out:
        # steady losing at the end isn't balance: more than 3% of the start a cycle
        checks['no late decline'] = out['late_slope'] > -0.03 * start
    elif checks:
        out['late_slope'] = None
    out['checks'] = checks
    out['complete'] = cycles >= MIN_CYCLES
    # too few days can't pass or fail a long-world gate; the checks are still there to read
    out['pass'] = None if not checks or not out['complete'] else all(checks.values())
    out['status'] = 'no gate' if not checks else 'incomplete' if not out['complete'] else 'pass' if out['pass'] else 'fail'
    return out


def kind_of(ratio: float, gate: str) -> str:
    if gate != 'auto':
        return gate
    return 'rich' if ratio >= 1.4 else 'lean' if ratio <= 0.9 else 'none'


def job(cfg: Config, world: str, policy: str, label: str, a: argparse.Namespace) -> dict:
    run = simulate(cfg, policy, a.seeds, a.cycles, a.every, a.seed)
    d = supply.describe(cfg, a.duty)
    picks = np.array(run['picks'])[-1]
    d['harvest'] = float(np.median(picks) / (d['grown'] * a.cycles)) if d['grown'] else None
    run.update(world=world, policy=policy, label=label, supply=d,
               gates=gates(run, d['start'], kind_of(d['ratio'], a.gate), d['cycle']),
               dials={'food_count': cfg.food.count, 'regrow': [cfg.food.regrow_min, cfg.food.regrow_max],
                      'patches': cfg.food.patches, 'patch_radius': cfg.food.patch_radius, 'meadows': cfg.grass.meadows},
               args={'seeds': a.seeds, 'cycles': a.cycles, 'seed': a.seed})
    return run


def settings(a: argparse.Namespace):
    for path in a.worlds:
        base = adjust(load(path), a)
        name = Path(path).stem
        for ratio in a.supply or [None]:
            for by in (a.by if ratio else ['as is']):
                cfg = supply.fit(base, ratio, by, a.duty) if ratio else base
                for policy in a.policy:
                    extra = f'supply {ratio} by {by}' if ratio else 'as written'
                    yield cfg, name, policy, f'{name} / {policy} / {extra}'


def main():
    p = argparse.ArgumentParser(description='scripted colonies in a world with no end: does it hold a population?')
    p.add_argument('worlds', nargs='+')
    p.add_argument('--policy', nargs='+', default=['forager'], choices=sorted(POLICY))
    p.add_argument('--seeds', type=int, default=16)
    p.add_argument('--cycles', type=float, default=10)
    p.add_argument('--every', type=float, default=10.0, help='seconds of world time between samples')
    p.add_argument('--seed', type=int, default=SEED)
    p.add_argument('--supply', type=float, nargs='+', help='supply ratios to land on, each by every --by dial')
    p.add_argument('--by', nargs='+', default=['count'], choices=['count', 'regrow'])
    p.add_argument('--duty', type=float, default=supply.DUTY, help='share of the day a nim walks, in the need')
    p.add_argument('--gate', default='auto', choices=['auto', 'rich', 'lean', 'none'])
    p.add_argument('--food-count', type=int)
    p.add_argument('--regrow', type=float, nargs=2, metavar=('MIN', 'MAX'))
    p.add_argument('--patches', type=int)
    p.add_argument('--patch-radius', type=float)
    p.add_argument('--grass', type=float, nargs=4, metavar=('MEADOWS', 'RADIUS', 'DISTANCE', 'REGROW'), help='meadows on, bite 0.25, food 0.4')
    p.add_argument('--jobs', type=int, default=1, help='runs at once, one process each')
    p.add_argument('--out', type=Path, help='folder for balance.json')
    a = p.parse_args()

    todo = list(settings(a))
    if a.jobs > 1:
        with ProcessPoolExecutor(a.jobs) as pool:
            runs = list(pool.map(job, *zip(*[(c, w, pol, lab, a) for c, w, pol, lab in todo])))
    else:
        runs = [job(c, w, pol, lab, a) for c, w, pol, lab in todo]
    for r in runs:
        report(r)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / 'balance.json').write_text(json.dumps({'runs': runs}))
        print(f'wrote {a.out / "balance.json"}')


def report(r: dict):
    g, s = r['gates'], r['supply']
    verdict = {'no gate': 'no gate', 'pass': 'PASS', 'fail': 'FAIL', 'incomplete': f'INCOMPLETE (under {MIN_CYCLES} days)'}[g['status']]
    late = 'n/a' if g.get('late_slope') is None else f'{g["late_slope"]:+.2f}/cycle'
    print(f'{r["label"]}: ratio {s["ratio"]:.2f} (foods {s["grown"]:.0f}+grass {s["grass"]:.0f} vs need {s["need"]:.0f}) | '
          f'end {g["end_median"]:.0f}/{g["start"]} ({g["end_share"]:.0%}), day2 {g["day2_share"]:.0%}, peak {g["peak_median"]:.0f}, '
          f'extinct {g["extinct_games"]}/{g["games"]} games and {g["extinct_colonies"]}/{g["games"] * g["colonies"]} colonies, late {late}, harvest {s["harvest"]:.0%} | {verdict} '
          f'{[k for k, v in g["checks"].items() if not v] or ""} | {r["speed"]:.0f} world-s/wall-s ({r["args"]["seeds"]} games)')


if __name__ == '__main__':
    main()
