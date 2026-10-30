# How good a brain is at each nursery game, scored the same way for every game so the calls we make on them hold up:
#
#   uv run python -m terrarium.games tag --brain A.pt B.pt [--config W.toml] [--episodes 128] [--held-out] [--out f.json]
#
# Every game plays the brain in each of its roles against fixed opponents (random walkers, or a scripted player that
# knows everything), and against itself. Each arena is one episode, and every brain plays the same worlds (same seed,
# same starts), so two brains can be compared episode by episode. Each number comes with a 95% interval (bootstrap
# over episodes), and every brain after the first is set against it: the mean difference, its interval, and whether
# the two can be told apart at all. A difference whose interval holds 0 is noise, however big it looks.
#
# This only covers the noise of scoring. Two training runs of the same setup can land far apart too, so a setup is
# judged on its seeds together (several brains, each scored here), never on one brain.

import argparse
import json
import multiprocessing as mp
from pathlib import Path
from typing import Callable

import numpy as np
import torch

from . import config, maze
from .evals import HELD_OUT, SEED, brain_policy, random_policy
from .physics import BLOCKS
from .schema import ACTIONS
from .world import World

Make = Callable[[World], Callable[[World], np.ndarray]]
EPISODES = 128
CI = 0.95
SPRINT = 2.5


def padded(make: Make) -> Make:
    """A policy's actions padded to today's list: actions a brain predates are always no."""
    def build(world):
        act = make(world)

        def go(w):
            x = act(w)
            if x.shape[-1] < len(ACTIONS):
                x = np.concatenate([x, -np.ones((*x.shape[:-1], len(ACTIONS) - x.shape[-1]))], -1)
            return x[..., :len(ACTIONS)]
        return go
    return build


def chaser(world: World):
    """Tag's scripted it: runs (and sprints, once close) at the nearest one it may tag, always knowing where all are."""
    def act(w):
        out = np.zeros((w.arenas, len(w.colony), len(ACTIONS)))
        out[..., 2:] = -1
        it = w.tag.mask()
        for a in range(w.arenas):
            i = int(np.flatnonzero(it[a])[0]) if it[a].any() else 0
            d = w.pos[a] - w.pos[a, i]
            others = np.arange(len(d))
            fair = w.alive[a] & (others != i)
            gap = np.where(fair, np.hypot(d[:, 0], d[:, 1]), np.inf)
            j = int(gap.argmin())
            want = (np.arctan2(d[j, 1], d[j, 0]) - w.heading[a, i] + np.pi) % (2 * np.pi) - np.pi
            out[a, i, 0], out[a, i, 1] = 1.0, np.clip(want * 3, -1, 1)
            out[a, i, ACTIONS.index('sprint')] = 1.0 if gap[j] < SPRINT else -1.0
        return out
    return act


def play(cfg, episodes: int, seed: int, parts: list[tuple[Callable[[World], np.ndarray], Make]], watch=None,
         brain: tuple[int, ...] = (0,)) -> tuple[World, np.ndarray]:
    """Every arena through one episode, each creature steered by the first part whose mask (world → (arenas,
    creatures) bool, read every tick) holds it. watch(world, tick) runs after each tick. Also the metres a minute
    walked by each arena's creatures in the brain's parts, on average."""
    w = World(cfg, episodes, seed)
    acts = [(mask, padded(make)(w)) for mask, make in parts]
    walked, ticks = np.zeros(episodes), np.zeros(episodes)
    for t in range(w.episode_ticks):
        x = np.zeros((*w.alive.shape, len(ACTIONS)))
        taken, ours = np.zeros(w.alive.shape, bool), np.zeros(w.alive.shape, bool)
        for k, (mask, act) in enumerate(acts):
            m = mask(w) & ~taken
            x = np.where(m[..., None], act(w), x)
            taken |= m
            if k in brain:
                ours |= m
        before = w.pos.copy()
        w.step(x)
        ours &= w.alive
        walked += (np.hypot(*(w.pos - before).transpose(2, 0, 1)) * ours).sum(1)
        ticks += ours.sum(1)
        if watch:
            watch(w, t)
    return w, walked / np.maximum(ticks, 1) * cfg.tick_hz * 60


everyone = lambda w: np.ones(w.alive.shape, bool)


def hidden_from_it(w: World) -> tuple[np.ndarray, np.ndarray]:
    """Per arena: runners with a block between them and whoever's it, and runners looked at."""
    out, n = np.zeros(w.arenas), np.zeros(w.arenas)
    assert w.tag
    for a, space in enumerate(w.physics.spaces):
        i = w.tag.it[a]
        for j in np.flatnonzero(w.alive[a]):
            if j != i:
                out[a] += space.segment_query_first(tuple(w.pos[a, i]), tuple(w.pos[a, j]), 0, BLOCKS) is not None
                n[a] += 1
    return out, n


def tag(cfg, it: Make, runner: Make, episodes: int, seed: int) -> dict[str, np.ndarray]:
    hid, looked = np.zeros(episodes), np.zeros(episodes)

    def watch(w, t):
        if len(cfg.block) and t % (cfg.tick_hz // 2) == 0:
            h, n = hidden_from_it(w)
            hid[:], looked[:] = hid + h, looked + n
    w, walked = play(cfg, episodes, seed, [(lambda w: w.tag.mask(), it), (everyone, runner)], watch,  # type: ignore[union-attr]
                     brain=(0, 1) if it is runner else (1,) if it is chaser else (0,))
    assert w.tag
    out = {'tags_a_minute': w.tag.tags.sum(1) / (cfg.episode.seconds / 60), 'walked': walked}
    if len(cfg.block):
        out['hidden'] = hid / np.maximum(looked, 1)
    return out


def seek(cfg, hider: Make, seeker: Make, episodes: int, seed: int) -> dict[str, np.ndarray]:
    w, walked = play(cfg, episodes, seed, [(lambda w: np.broadcast_to(w.seek.seeker, w.alive.shape), seeker),  # type: ignore[union-attr]
                                           (everyone, hider)],
                     brain=(0, 1) if hider is seeker else (0,) if hider is random_policy else (1,))
    assert w.seek
    return {'seen': w.seek.seen / np.maximum(w.seek.played, 1), 'walked': walked}


def flag(cfg, ours: Make, theirs: Make, episodes: int, seed: int) -> dict[str, np.ndarray]:
    """Colony 0 is ours. Played twice, the second time with the sides swapped, so neither base is favoured; each
    episode's numbers are the two games added (captures for less against, pickups and games with a pickup ours)."""
    out = {}
    for us in (0, 1):
        w, walked = play(cfg, episodes, seed, [(lambda w, us=us: np.broadcast_to(w.colony == us, w.alive.shape), ours),
                                               (everyone, theirs)], brain=(0, 1) if ours is theirs else (0,))
        f = w.flags
        assert f
        game = {'captures': f.captures[:, us] - f.captures[:, 1 - us], 'pickups': f.pickups[:, us],
                'saves': f.saves[:, us], 'took_one': (f.pickups[:, us] > 0).astype(float), 'walked': walked}
        out = {k: out.get(k, 0) + v / 2 for k, v in game.items()}
    return out


def peek(cfg, player: Make, episodes: int, seed: int) -> dict[str, np.ndarray]:
    w, walked = play(cfg, episodes, seed, [(everyone, player)])
    p = w.peek
    assert p
    return {'found_a_minute': p.found / (cfg.episode.seconds / 60), 'found': p.found / np.maximum(p.found + p.missed, 1),
            'wait': p.waited / np.maximum(p.found, 1) / cfg.tick_hz, 'walked': walked}


def maze_game(cfg, player: Make, episodes: int, seed: int) -> dict[str, np.ndarray]:
    w, walked = play(cfg, episodes, seed, [(everyone, player)])
    return {'berries_a_minute': w.meals.sum(1) / (cfg.episode.seconds / 60), 'walked': walked}


def still(world: World):
    """Stands where it starts: what doing nothing scores, which a cost on moving makes look good."""
    def act(w):
        out = np.full((*w.alive.shape, len(ACTIONS)), -1.0)
        out[..., :2] = 0
        return out
    return act


def last_seen(world: World):
    """Peekaboo with a perfect memory and nothing else: walks to where it last had the berry in sight, and wanders at
    random until it sees one. Once there it forgets the spot: it has eaten the berry or found it gone (waiting there
    for good stood still for the rest of a game whenever the next berry landed out of sight)."""
    from .vision import FOOD, look
    spot = np.full((*world.alive.shape, 2), np.nan)
    wander = random_policy(world)

    def act(w):
        sight = look(w)
        sees = (sight.kind == FOOD).any(-1)
        spot[sees] = np.broadcast_to(w.food_pos[:, None, 0], spot.shape)[sees]
        out = wander(w)
        if out.shape[-1] < len(ACTIONS):
            out = np.concatenate([out, -np.ones((*out.shape[:-1], len(ACTIONS) - out.shape[-1]))], -1)
        d = spot - w.pos
        far = np.hypot(d[..., 0], d[..., 1]) > 0.3
        spot[~far] = np.nan
        known = ~np.isnan(spot[..., 0])
        want = (np.arctan2(d[..., 1], d[..., 0]) - w.heading + np.pi) % (2 * np.pi) - np.pi
        out[..., 0] = np.where(known, np.where(far, np.where(np.abs(want) < 1, 1.0, 0.2), 0.0), out[..., 0])
        out[..., 1] = np.where(known, np.where(far, np.clip(want * 3, -1, 1), 0.0), out[..., 1])
        return out
    return act


# each game: its world, its roles (what the brain plays, against what), the number that matters most in each role
# and which way is better
GAMES = {
    'tag': ('nursery-tag.toml', {
        'catch': (lambda b: (tag, b, random_policy), 'tags_a_minute', +1),
        'escape': (lambda b: (tag, chaser, b), 'tags_a_minute', -1),
        'self': (lambda b: (tag, b, b), 'tags_a_minute', +1),
    }),
    'seek': ('nursery-seek.toml', {
        'seek': (lambda b: (seek, random_policy, b), 'seen', +1),
        'hide': (lambda b: (seek, b, random_policy), 'seen', -1),
        'self': (lambda b: (seek, b, b), 'seen', +1),
    }),
    'flag': ('nursery-flag.toml', {
        'random': (lambda b: (flag, b, random_policy), 'captures', +1),
        'self': (lambda b: (flag, b, b), 'pickups', +1),
    }),
    'peek': ('nursery-peek-again.toml', {'find': (lambda b: (peek, b), 'found_a_minute', +1)}),
    'maze': ('nursery-maze.toml', {'find': (lambda b: (maze_game, b), 'berries_a_minute', +1)}),
}
BASELINES = {'random': random_policy, 'chaser': chaser, 'still': still, 'last_seen': last_seen, 'wall': maze.wall_policy,
             'mapped': maze.mapped_policy}


def interval(values: np.ndarray, rng: np.random.Generator, draws: int = 2000) -> tuple[float, float]:
    """The bootstrap 95% interval of the mean."""
    if len(values) < 2:
        return float('nan'), float('nan')
    means = values[rng.integers(0, len(values), (draws, len(values)))].mean(1)
    lo, hi = np.quantile(means, [(1 - CI) / 2, (1 + CI) / 2])
    return float(lo), float(hi)


def summary(values: np.ndarray) -> dict:
    lo, hi = interval(values, np.random.default_rng(0))
    return {'mean': float(values.mean()), 'low': lo, 'high': hi, 'episodes': len(values)}


def against(a: np.ndarray, b: np.ndarray) -> dict:
    """b less a, episode by episode (the same worlds), with its interval: apart when the interval misses 0."""
    d = b - a
    lo, hi = interval(d, np.random.default_rng(1))
    return {'difference': float(d.mean()), 'low': lo, 'high': hi, 'apart': bool(lo > 0 or hi < 0)}


def policy(name: str, wiped: float | None = None) -> Make:
    """wiped: None keeps a memory brain's notes, 0 blanks them before every choice, more blanks them that many
    seconds apart."""
    if name in BASELINES:
        return BASELINES[name]
    return brain_policy(name, wiped=wiped == 0, wipe_every=wiped or 0.0)


def wiped_name(wiped: float | None) -> str:
    return '' if wiped is None else ' wiped' if wiped == 0 else f' wiped every {wiped:g} s'


def score_one(job: tuple) -> dict:
    game, role, who, wiped, world, episodes, seed = job
    torch.set_num_threads(1)
    cfg = config.load(world)
    fn, *makes = GAMES[game][1][role][0](policy(who, wiped))
    return {k: v.astype(float).tolist() for k, v in fn(cfg, *makes, episodes, seed).items()}


def score(game: str, players: list[str], world: str | None = None, episodes: int = EPISODES, seed: int = SEED,
          wiped: bool = False, processes: int | None = None, wipe_every: float = 0.0) -> dict:
    """Every player (a brain's path, or a baseline's name) in every role, each in its own process."""
    default, roles = GAMES[game]
    world = world or str(config.DEFAULT.parent / default)
    names: list[tuple[str, float | None]] = [(p, None) for p in players]
    remembers = [p for p in players if p not in BASELINES and brain_memory(p)]
    if wiped:
        names += [(p, 0.0) for p in remembers]
    if wipe_every:
        names += [(p, wipe_every) for p in remembers]
    jobs = [(game, role, p, w, world, episodes, seed) for p, w in names for role in roles]
    with mp.get_context('spawn').Pool(processes or min(len(jobs), max(1, (mp.cpu_count() or 2) - 1))) as pool:
        done = pool.map(score_one, jobs)
    out = {'game': game, 'world': world, 'seed': seed, 'episodes': episodes, 'players': {}}
    for (_, role, p, w, *_), values in zip(jobs, done):
        out['players'].setdefault(p + wiped_name(w), {})[role] = values
    return out


def brain_memory(path: str) -> int:
    return torch.load(path, weights_only=True).get('shape', {}).get('memory', 0)


def labels(players: list[str]) -> dict[str, str]:
    """A short name per player: its file name, or its run's folder where two brains share a file name (every run's
    last checkpoint is named by its sample count)."""
    paths = {p: Path(p.split(' wiped')[0]) for p in players}
    files = [path.name for path in set(paths.values())]
    out = {}
    for p, path in paths.items():
        name = path.name
        if files.count(name) > 1:
            name = path.parent.parent.name if path.parent.name == 'checkpoints' else str(path)
        out[p] = name + p[len(str(path)):] if p.startswith(str(path)) else name
    return out


def report(result: dict) -> str:
    """A table: each player's main number per role with its interval, then each against the first."""
    _, roles = GAMES[result['game']]
    players = result['players']
    lines = [f"{result['game']} in {Path(result['world']).name}, {result['episodes']} episodes from seed {result['seed']}"]
    head = ''.join(f'{f"{r}: {roles[r][1]} {"↑" if roles[r][2] > 0 else "↓"}":>34}' for r in roles)
    lines.append(f'{"":>32}{head}')
    first = next(iter(players))
    label = labels(list(players))
    for name, got in players.items():
        cells = ''
        for r, (_, key, _) in roles.items():
            s = summary(np.array(got[r][key]))
            cells += f'{s["mean"]:>14.3f} [{s["low"]:.3f}, {s["high"]:.3f}]'.rjust(34)
        lines.append(f'{label[name][-32:]:>32}{cells}')
    for name, got in list(players.items())[1:]:
        cells = ''
        for r, (_, key, way) in roles.items():
            c = against(np.array(players[first][r][key]), np.array(got[r][key]))
            mark = ('better' if c['difference'] * way > 0 else 'worse') if c['apart'] else 'can’t tell'
            cells += f'{c["difference"]:+.3f} [{c["low"]:+.3f}, {c["high"]:+.3f}] {mark}'.rjust(34)
        lines.append(f'{("vs " + label[first])[-32:]:>32}' if name == list(players)[1] else '')
        lines.append(f'{label[name][-32:]:>32}{cells}')
    return '\n'.join(l for l in lines if l)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('game', choices=sorted(GAMES))
    parser.add_argument('--brain', nargs='*', default=[], help='checkpoints to score')
    parser.add_argument('--baseline', nargs='*', default=['random'], choices=sorted(BASELINES),
                        help='scripted players scored alongside, first (the first player is what the rest are set against)')
    parser.add_argument('--config', help="the game's world (default: its nursery)")
    parser.add_argument('--episodes', type=int, default=EPISODES)
    parser.add_argument('--held-out', action='store_true', help=f'seed {HELD_OUT} instead of {SEED}')
    parser.add_argument('--wiped', action='store_true',
                        help='also score brains with memory with their notes wiped before every choice')
    parser.add_argument('--wiped-every', type=float, default=0.0, metavar='SECONDS',
                        help='also score brains with memory with their notes wiped this many seconds apart')
    parser.add_argument('--processes', type=int)
    parser.add_argument('--out', help='every episode\'s numbers as JSON')
    args = parser.parse_args()
    result = score(args.game, args.baseline + args.brain, args.config, args.episodes,
                   HELD_OUT if args.held_out else SEED, args.wiped, args.processes, args.wiped_every)
    print(report(result))
    if args.out:
        Path(args.out).write_text(json.dumps(result) + '\n')


if __name__ == '__main__':
    main()
