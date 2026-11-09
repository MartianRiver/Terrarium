# A world's energy budget, printed: what staying alive and walking cost, how long a nim lasts, and what a trip to the
# food costs against what it brings home. `python -m terrarium.budget WORLD.toml [--arenas 64]`.
# The aim is trips that return about 5x their cost (docs/training.md, "Energy budget"); distances come from building
# the world and reading where things landed, not from the config.
import argparse
import numpy as np

from .config import Config, load
from .world import World

INF = float('inf')


def rates(cfg: Config, share: float = 1.0) -> dict:
    """Energy a second, by state and light: day, dark outside and dark in the nest (a nim alone, no huddle).
    The crop costs nothing to carry, it only slows the walk."""
    e, n = cfg.energy, cfg.night
    cold = {'day': 0.0}
    if n.on and n.cold > 0:
        cold = {'day': 0.0, 'dark out': n.cold, 'dark nest': n.cold * (1 - min(1.0, n.nest))}
    elif n.on:
        cold = {'day': 0.0, 'dark out': 0.0, 'dark nest': 0.0}
    still = {k: (e.drain + c) * share for k, c in cold.items()}
    thrust = {k: (e.drain + c + e.move) * share for k, c in cold.items()}
    return {'resting': still, 'full thrust': thrust, 'full thrust, full crop': dict(thrust)}


def lasts(energy: float, rate: float) -> float:
    return energy / rate if rate > 0 else INF


def trip(cfg: Config, dist: float, young: bool = False) -> dict:
    """A trip to food `dist` m (nest centre to food, as the crow flies) and home with a full crop, by day, at full thrust
    the whole way: out unladen, back slowed by the crop. The walk is a little shorter in practice (the nest's edge and
    the food's reach, ~2 m, aren't walked), so the cost reads a touch high."""
    e, share = cfg.energy, cfg.young.energy if young else 1.0
    out = cfg.creature.max_speed * (cfg.young.speed if young else 1.0)
    back = out * (1 - cfg.crop.slow * cfg.crop.capacity)
    secs = dist / out + (dist / back if back > 0 else INF)
    walking, alive = e.move * share * secs, e.drain * share * secs
    # an apple hangs out of reach: taking it costs a jump
    hop = cfg.jump.energy * share if cfg.tree.on else 0.0
    cost = walking + alive + hop
    food = cfg.crop.capacity * e.food
    jelly = cfg.crop.capacity * cfg.jelly.energy
    return {'dist': dist, 'secs': secs, 'walking': walking, 'alive': alive, 'hop': hop, 'cost': cost,
            'home': food, 'home jelly': jelly,
            'return': food / cost if cost > 0 else INF, 'return jelly': jelly / cost if cost > 0 else INF,
            'out speed': out, 'back speed': back}


def day(cfg: Config, food_secs: float, pond_secs: float | None) -> dict:
    """Share of a day an adult spends keeping itself fed and watered, at full thrust on trips and resting otherwise:
    itself only (no store, no young), food waiting where it lies (no searching), every pond trip drinks 0.7 of a bar.
    Walking on any trip costs `move`, so the food share is solved with the pond walking in it."""
    e, w = cfg.energy, cfg.water
    pond_walk = drinking = 0.0
    if pond_secs is not None and w.on:
        need = w.drain                      # bars a second
        pond_walk = need / 0.7 * pond_secs
        drinking = need / (w.drink - w.drain) if w.drink > w.drain else INF
    k = food_secs / (cfg.crop.capacity * e.food) if cfg.crop.capacity else INF
    food = k * (e.drain + e.move * pond_walk) / (1 - k * e.move) if k * e.move < 1 else INF
    return {'food trips': food, 'pond trips': pond_walk, 'drinking': drinking,
            'left': 1 - food - pond_walk - drinking if INF not in (food, drinking) else -INF}


def pair_distances(world: World, points: np.ndarray, per: str = 'any') -> np.ndarray:
    """From each nest to points (arenas, k, 2), all arenas and nests pooled: to every one, or to the nearest."""
    d = np.hypot(points[:, None, :, 0] - world.nests[None, :, None, 0],
                 points[:, None, :, 1] - world.nests[None, :, None, 1])
    return d.min(-1).ravel() if per == 'nearest' else d.ravel()


def spread(d: np.ndarray) -> tuple[float, float]:
    return float(np.percentile(d, 50)), float(np.percentile(d, 90))


def budget(cfg: Config, arenas: int = 64, seed: int = 0) -> dict:
    groups = {'adult': False, 'young': True} if cfg.young.on else {'adult': False}
    out: dict = {'groups': {}, 'arenas': arenas}
    for name, young in groups.items():
        share = cfg.young.energy if young else 1.0
        r = rates(cfg, share)
        g = {'rates': r, 'lasts': {}}
        for state in ('resting', 'full thrust'):
            g['lasts'][state] = {k: {'start': lasts(cfg.energy.start, v), 'full': lasts(1.0, v)}
                                 for k, v in r[state].items()}
        if cfg.water.on:
            drain = cfg.water.drain * share
            g['water'] = {'start': lasts(cfg.water.start, drain), 'full': lasts(1.0, drain)}
        out['groups'][name] = g

    world = World(cfg, arenas, seed)
    food = world.food_pos[:, :world.wild]
    out['food'] = {'what': 'apple' if cfg.tree.on else 'food', 'pieces': world.wild}
    for per in ('any', 'nearest'):
        d50, d90 = spread(pair_distances(world, food, per))
        out['food'][per] = {name: [trip(cfg, d, young) if cfg.crop.capacity > 0 else None for d in (d50, d90)]
                            for name, young in groups.items()}
    if world.ponds:
        # a drink needs the centre in the pond, so the walk ends at its edge
        d50, d90 = spread(pair_distances(world, world.ponds.pos, 'nearest'))
        edge = cfg.water.radius
        pond = {}
        for name, young in groups.items():
            share = cfg.young.energy if young else 1.0
            top = cfg.creature.max_speed * (cfg.young.speed if young else 1.0)
            legs = []
            for d in (d50, d90):
                secs = 2 * max(d - edge, 0) / top
                legs.append({'dist': d, 'secs': secs, 'water': cfg.water.drain * share * secs,
                             'energy': (cfg.energy.drain + cfg.energy.move) * share * secs})
            pond[name] = legs
        out['pond'] = pond
    food_secs = out['food']['any']['adult'][0]['secs'] if cfg.crop.capacity else INF
    pond_secs = out['pond']['adult'][0]['secs'] if 'pond' in out else None
    out['day'] = day(cfg, food_secs, pond_secs)
    if cfg.water.on:
        out['refill'] = 1 / (cfg.water.drink - cfg.water.drain) if cfg.water.drink > cfg.water.drain else INF
    return out


def fmt(x: float, places: int = 3) -> str:
    return '-' if x == INF else f'{x:.{places}f}'


def secs(x: float) -> str:
    return 'never' if x == INF else f'{x:.1f}' if x < 10 else f'{x:.0f}'


def show(cfg: Config, b: dict, name: str = '') -> str:
    lines = [f'{name or "world"}: {cfg.colonies.count} colonies of {cfg.colonies.size}, {b["arenas"]} arenas'
             + (', nights on' if cfg.night.on else '') + (', young on' if cfg.young.on else '')]
    for who, g in b['groups'].items():
        note = f' (young for {cfg.young.seconds:.0f} s, costs x{cfg.young.energy:g})' if who == 'young' else ''
        cols = list(g['rates']['resting'])
        lines += ['', f'{who}{note}: energy a second'.ljust(34) + ''.join(c.rjust(11) for c in cols)]
        for state, row in g['rates'].items():
            lines.append(f'  {state}'.ljust(34) + ''.join(fmt(row[c], 4).rjust(11) for c in cols))
        lines.append(f'  a nim lasts, seconds'.ljust(34) + 'from start'.rjust(11) + 'from full'.rjust(11))
        for state, row in g['lasts'].items():
            for c in cols:
                if c == 'dark nest' and row[c]['full'] == g['lasts'][state]['day']['full']:
                    continue
                lines.append(f'    {state}, {c}'.ljust(34) + secs(row[c]['start']).rjust(11) + secs(row[c]['full']).rjust(11))
        if 'water' in g:
            lines.append(f'  water lasts, seconds'.ljust(34) + secs(g['water']['start']).rjust(11) + secs(g['water']['full']).rjust(11))

    f = b['food']
    if cfg.crop.capacity == 0:
        lines += ['', 'no crop: nothing is carried home, so there is no trip to price']
    for who in b['groups']:
        if cfg.crop.capacity == 0:
            break
        any_, near = f['any'][who], f['nearest'][who]
        t = any_[0]
        lines += ['', f'{who}: a trip to the {f["what"]} and home, full crop, by day'.ljust(50)
                  + 'any p50'.rjust(9) + 'any p90'.rjust(9) + 'near p50'.rjust(10) + 'near p90'.rjust(10)]
        rows = [('metres, nest centre to it', 'dist', 2), ('seconds there and back', 'secs', 1),
                ('cost: walking', 'walking', 3), ('cost: staying alive', 'alive', 3)]
        if t['hop']:
            rows.append(('cost: the jump for it', 'hop', 3))
        rows += [('cost: all', 'cost', 3), ('brought home (as food)', 'home', 2), ('  as jelly', 'home jelly', 2),
                 ('return, food / cost', 'return', 1), ('return, jelly / cost', 'return jelly', 1)]
        for label, key, places in rows:
            vals = [x[key] for x in (*any_, *near)]
            lines.append(f'  {label}'.ljust(50) + ''.join(fmt(v, places).rjust(w) for v, w in zip(vals, (9, 9, 10, 10))))
        lines.append(f'  speed out {t["out speed"]:.2f} m/s, back laden {t["back speed"]:.2f} m/s; '
                     f'"any" is every {f["what"]} piece ({f["pieces"]}) from every nest, "near" the nearest to each nest')

    if 'pond' in b:
        for who, legs in b['pond'].items():
            lines += ['', f'{who}: a pond and back'.ljust(50) + 'p50'.rjust(9) + 'p90'.rjust(9)]
            for label, key, places in (('metres, nest centre to the nearest pond', 'dist', 2), ('seconds there and back', 'secs', 1),
                                       ('water lost on the way', 'water', 3), ('energy spent on the way', 'energy', 3)):
                lines.append(f'  {label}'.ljust(50) + ''.join(fmt(l[key], places).rjust(9) for l in legs))
    if 'refill' in b:
        lines.append(f'  adult: empty to full in a pond, seconds'.ljust(50) + ('never' if b['refill'] == INF else secs(b['refill'])).rjust(9))
    d = b['day']
    lines += ['', 'adult: a day, keeping itself fed and watered (median trips; itself only, food waiting, no searching)']
    for label, key in (('food trips', 'food trips'), ('pond trips', 'pond trips'), ('drinking', 'drinking'),
                       ('left for anything else', 'left')):
        v = d[key]
        lines.append(f'  {label}'.ljust(50) + ('never keeps up' if abs(v) == INF else f'{v:.0%}').rjust(14))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="A world's energy budget: costs, how long a nim lasts, what a trip returns.")
    parser.add_argument('world')
    parser.add_argument('--arenas', type=int, default=64)
    args = parser.parse_args()
    cfg = load(args.world)
    print(show(cfg, budget(cfg, args.arenas), args.world.rsplit('/', 1)[-1]))


if __name__ == '__main__':
    main()
