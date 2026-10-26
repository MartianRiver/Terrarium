# Evals v2: a policy plays a fixed set of episodes on fixed seeds, one per
# arena, and gets food per minute and time alive, plus what a colony needs
# looked at: food stored, jelly eaten, who died beside a stocked nest, whole
# colonies lost, and how often each yes/no action is taken where it matters.
# Errors are over arenas, since creatures sharing one aren't independent. Random actions
# are the baseline every brain has to beat; greedy is a scripted forager that
# heads for the nearest food it can see, there to show what the senses allow,
# eating what it carries once it can without waste. Carrier is greedy that takes
# its crop home and unloads it once it's full, and goes home to eat when it's
# hungry and there's jelly in the store. Nester is carrier that heads home when
# the light starts to fade and waits in the nest until it's full day.
#
#   uv run python -m terrarium.evals --policy random greedy --config configs/solo.toml [--brain X.pt] [--modes drawn mean sampled]
#                                    [--device cuda]
#
# Each policy (and each brain in each mode) is scored in its own process, side by side.

import argparse
import json
import multiprocessing as mp
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import torch

from .brain import load as load_brain
from .config import DEFAULT, Config, load
from .forage import observe
from .log import Logger
from .random_actions import RandomActions
from .runs import cpu_quota
from .schema import YES_NO
from .vision import FOOD, NOTHING, look
from .world import World

log = Logger('evals')

# far from any seed training uses, so a brain is never scored on worlds it trained on
SEED = 1_000_000
# kept for promotion: nothing gets tuned while looking at it
HELD_OUT = 2_000_000
EPISODES = 64
# a meal is contested when a creature of another colony is this close to the food as it goes (metres)
SNATCH = 1.5

Policy = Callable[[World], np.ndarray]


def random_policy(world: World) -> Policy:
    act = RandomActions(world.arenas, len(world.colony), SEED)
    return lambda _: act()


def greedy_policy(world: World) -> Policy:
    v = world.cfg.vision
    angles = np.linspace(-v.fov / 2, v.fov / 2, v.rays)
    ahead = np.abs(angles) < 0.5

    def act(w: World) -> np.ndarray:
        sight = look(w)
        dist, kind = sight.dist, sight.kind
        food = np.where(kind == FOOD, dist, np.inf)
        nearest = food.argmin(-1)
        sees = np.isfinite(food.min(-1))
        # nothing to eat in view: go straight, and turn hard when something's close ahead
        blocked = (np.where(ahead & (kind != NOTHING), dist, np.inf).min(-1) < 1.5)
        turn = np.where(sees, np.clip(angles[nearest] * 3, -1, 1), np.where(blocked, 1.0, 0.0))
        eat = np.where(w.energy <= 1 - w.cfg.energy.food, 1.0, -1.0)
        return np.stack([np.ones_like(turn), turn, -np.ones_like(turn), eat], -1)
    return act


def carrier_policy(world: World) -> Policy:
    greedy = greedy_policy(world)

    def act(w: World) -> np.ndarray:
        action = greedy(w)
        home = w.nests[w.colony] - w.pos
        bearing = np.arctan2(home[..., 1], home[..., 0]) - w.heading
        bearing = (bearing + np.pi) % (2 * np.pi) - np.pi
        stocked = np.take_along_axis(w.store, np.broadcast_to(w.colony, w.crop.shape), 1) > 0
        home_now = (w.crop >= w.cfg.crop.capacity) | ((w.energy < w.cfg.jelly.hunger) & stocked)
        action[..., 1] = np.where(home_now, np.clip(bearing * 3, -1, 1), action[..., 1])
        action[..., 2] = np.where((w.nest_at() == w.colony) & (w.crop > 0), 1.0, -1.0)
        hungry = w.energy < w.cfg.jelly.hunger
        action[..., 3] = np.where(hungry | (action[..., 3] > 0), 1.0, -1.0)
        return action
    return act


def nester_policy(world: World) -> Policy:
    carrier = carrier_policy(world)

    def act(w: World) -> np.ndarray:
        action = carrier(w)
        # from the first dimming of dusk until full day: home, and wait in the nest (eating jelly when hungry)
        evening = (w.light() < 1)[:, None] & np.ones_like(w.alive)
        home = w.nests[w.colony] - w.pos
        bearing = np.arctan2(home[..., 1], home[..., 0]) - w.heading
        bearing = (bearing + np.pi) % (2 * np.pi) - np.pi
        inside = w.nest_at() == w.colony
        action[..., 0] = np.where(evening, np.where(inside, 0.0, 1.0), action[..., 0])
        action[..., 1] = np.where(evening, np.clip(bearing * 3, -1, 1), action[..., 1])
        return action
    return act


POLICIES = {'random': random_policy, 'greedy': greedy_policy, 'carrier': carrier_policy, 'nester': nester_policy}

# where a yes/no action is worth watching: (who's in that spot, the action's index)
CONTEXTS = {
    'unload_home': (lambda w, nest, mine: (nest == w.colony) & (w.crop > 0), 2),
    'unload_away': (lambda w, nest, mine: (nest < 0) & (w.crop > 0), 2),
    'eat_hungry_crop': (lambda w, nest, mine: (w.crop > 0) & (w.energy < w.cfg.jelly.hunger), 3),
    # crop or not: a carrier home hungry unloads and eats jelly on the same tick
    'eat_hungry_home': (lambda w, nest, mine: (nest == w.colony) & (w.energy < w.cfg.jelly.hunger) & (mine > 0), 3),
    'sprint_ready': (lambda w, nest, mine: (w.sprinting == 0) & (w.resting == 0) & w.cfg.sprint.on, 4),
    'grab_block': (lambda w, nest, mine: w.touching_block() & w.cfg.grab.on, 5),
}
# how hard it turns (the mean of turn squared, what turning costs by) out by day and in its nest at night
PLACES = {
    'day_out': lambda w, home: ~home & (w.light() == 1)[:, None],
    'night_home': lambda w, home: home & w.dark[:, None],
}


# how a brain picks its actions: steering by its mean with yes/no actions drawn at the odds it gives them (what it does
# in replays), all by the mean, or all drawn as in training
MODES = ('drawn', 'mean', 'sampled')


def brain_policy(path: Path | str, mode: str = 'drawn', device: str = 'cpu') -> Callable[[World], Policy]:
    """A trained brain. Steering by its mean scores what it's learned, not its exploration; a yes/no action taken
    by its mean is never yes until it's sure, so it's drawn instead, with seeded noise so the numbers repeat."""
    brain, meta = load_brain(path)
    brain.eval().to(device)
    # it chooses every `repeat` ticks, as it did in training, and holds its choice in between
    repeat = meta.get('repeat', 1)
    spread = brain.log_std.detach().exp().cpu().numpy()
    yes_no = np.isin(brain.schema['actions'], YES_NO)
    if mode == 'drawn':
        spread = spread * yes_no
    elif mode == 'mean':
        spread = spread * 0
    # a brain whose yes/no actions are coins tosses them (drawn, sampled) or takes the likelier side (mean)
    coins = yes_no if brain.yes_no == 'bernoulli' else None
    if coins is not None:
        spread = spread * ~coins

    def make(world: World) -> Policy:
        last = np.zeros((world.arenas, len(world.colony), 2))
        noise = np.random.default_rng(SEED)
        held, ticks = None, 0

        def act(w: World) -> np.ndarray:
            nonlocal last, held, ticks
            if ticks % repeat == 0:
                mean = brain.act(observe(w, last), sample=False)
                mean = mean + spread * noise.standard_normal(mean.shape, dtype=mean.dtype)
                if coins is not None:
                    odds = mean[..., coins]
                    yes = odds > 0 if mode == 'mean' else noise.random(odds.shape) < 1 / (1 + np.exp(-odds))
                    mean[..., coins] = np.where(yes, 1.0, -1.0)
                held = np.clip(mean, -1, 1).reshape(*last.shape[:2], -1)
                last = held[..., :2]
            ticks += 1
            assert held is not None
            return held
        return act
    return make


def run(cfg: Config, make: Callable[[World], Policy], episodes: int = EPISODES, seed: int = SEED) -> dict:
    """Every episode to its end. Per-creature numbers with their means and errors, deaths, and action rates."""
    world = World(cfg, episodes, seed)
    policy = make(world)
    shape = world.alive.shape
    lived, meals, stored, jelly = (np.zeros(shape, int) for _ in range(4))
    # deaths in each slot: with hatching, one slot can die more than once
    died, beside_jelly, at_nest, in_dark, away_by_day = (np.zeros(shape, int) for _ in range(5))
    # dawns each creature lived to see, and the colonies with anyone left at the first one
    nights = np.zeros(shape, int)
    colonies = np.unique(world.colony)
    first_dawn = np.zeros((episodes, len(colonies)), bool)
    # colonies that were ever left with nobody, those still going when the episode ran its full length, and hatchlings
    emptied = np.zeros((episodes, len(colonies)), bool)
    at_end = np.zeros((episodes, len(colonies)), bool)
    hatched = np.zeros((episodes, len(colonies)), int)
    # Terrikins alive in each colony at the end, and the most it had at once
    size_end = np.zeros((episodes, len(colonies)), int)
    size_peak = np.zeros((episodes, len(colonies)), int)
    dawned = np.zeros(episodes, bool)
    actions = {k: [0, 0] for k in CONTEXTS}
    turning = {k: [0, 0.0] for k in PLACES}
    # food that grows in the middle patches (inside a vault, if the world has one), and how far blocks got moved
    f = np.arange(world.food_pos.shape[1])
    middle = (f < world.wild) & (f % max(cfg.food.patches, 1) < cfg.food.middle)
    from_middle = np.zeros(episodes, int)
    # meals of growing food, and those with a creature of another colony close by when it went
    meals_seen, contested = 0, 0
    start = np.array([(b.x, b.y) for b in cfg.block]).reshape(-1, 2)
    moved = np.zeros((episodes, len(cfg.block)))
    done = np.zeros(episodes, bool)
    while not done.all():
        before = world.alive & ~done[:, None]
        action = policy(world)
        mine = np.take_along_axis(world.store, np.broadcast_to(world.colony, shape), 1)
        nest = world.nest_at()
        home = nest == world.colony
        for name, (where, yes) in CONTEXTS.items():
            if action.shape[-1] > yes:
                seen = before & where(world, nest, mine)
                actions[name][0] += seen.sum()
                actions[name][1] += (seen & (action[..., yes] > 0)).sum()
        for name, where in PLACES.items():
            seen = before & where(world, home)
            turning[name][0] += seen.sum()
            turning[name][1] += (np.clip(action[..., 1], -1, 1) ** 2 * seen).sum()
        was_dark = world.dark.copy()
        by_day = world.light()[:, None] == 1
        growing = world.food_present & (f < world.wild)
        pos, food_pos = world.pos.copy(), world.food_pos.copy()
        world.step(action)
        # food goes at nightfall too; only count it eaten on other ticks
        eaten = growing & ~world.food_present & ~(world.dark & ~was_dark)[:, None] & ~done[:, None]
        from_middle += (eaten & middle).sum(1)
        for a, i in zip(*np.nonzero(eaten)):
            d = np.where(before[a], np.hypot(*(pos[a] - food_pos[a, i]).T), np.inf)
            rival = world.colony != world.colony[d.argmin()]
            meals_seen += 1
            contested += bool((d[rival] < SNATCH).any())
        lived += before
        dawn = was_dark & ~world.dark & ~done
        nights += dawn[:, None] & world.alive
        first = dawn & ~dawned
        if first.any():
            first_dawn[first] = np.stack([world.alive[:, world.colony == c].any(1) for c in colonies], 1)[first]
            dawned |= first
        gone = before & ~world.alive
        died += gone
        beside_jelly += gone & (mine > 0)
        at_nest += gone & home
        in_dark += gone & world.dark[:, None]
        away_by_day += gone & ~home & by_day
        counts = np.stack([world.alive[:, world.colony == c].sum(1) for c in colonies], 1)
        going = counts > 0
        size_peak = np.where(done[:, None], size_peak, np.maximum(size_peak, counts))
        emptied |= ~going & ~done[:, None]
        # an arena that has ended stops counting; the others carry on
        finished = world.ended & ~done
        meals[finished] = world.meals[finished]
        stored[finished] = world.stored[finished]
        jelly[finished] = world.jelly[finished]
        moved[finished] = np.hypot(*(world.block_pos[finished] - start).transpose(2, 0, 1))
        hatched[finished] = world.hatched[finished]
        size_end[finished] = counts[finished]
        at_end[finished] = going[finished] & (world.age[finished, None] >= world.episode_ticks)
        done |= finished
    # per starting place: a colony's room to grow shows in its size, not here
    starters = ~world.spare
    alive = lived[:, starters] / cfg.tick_hz
    per_minute = meals[:, starters] / (alive / 60)
    return {
        'episodes': episodes, 'seed': seed,
        'food_per_minute': summary(per_minute), 'seconds_alive': summary(alive),
        'food': summary(meals[:, starters]), 'stored': summary(stored[:, starters]), 'jelly': summary(jelly[:, starters]),
        'deaths': {'creatures': died.size, 'died': int(died.sum()), 'beside_jelly': int(beside_jelly.sum()),
                   'at_nest': int(at_nest.sum()), 'in_dark': int(in_dark.sum()), 'away_by_day': int(away_by_day.sum()),
                   'colonies': emptied.size, 'colonies_lost': int(emptied.sum())},
        # per colony an episode, and the colonies that hatched at least one
        'hatched': {**summary(hatched), 'colonies': int((hatched > 0).sum())},
        'colonies_to_the_end': int(at_end.sum()),
        'colony_size': {'start': cfg.colonies.size, 'end': summary(size_end), 'peak': summary(size_peak)},
        # colony by colony, summed or averaged over the episodes, for head-to-head evals (versus.py)
        'per_colony': {'to_the_end': at_end.sum(0).tolist(), 'lost': emptied.sum(0).tolist(),
                       'size_end': size_end.mean(0).tolist(), 'hatched': hatched.mean(0).tolist(),
                       'alive': [float(alive[:, world.colony[starters] == c].mean()) for c in colonies]},
        # with nights on: how many each lived through, and the colonies still going at the first dawn (None if the
        # episode is over before one)
        'nights': summary(nights),
        'through_first_night': int(first_dawn.sum()) if cfg.night.on and cfg.episode.seconds > cfg.night.cycle else None,
        'actions': {k: {'ticks': int(n), 'yes': y / n if n else None} for k, (n, y) in actions.items()},
        'turning': {k: float(t / n) if n else None for k, (n, t) in turning.items()},
        'from_middle': summary(from_middle[:, None]),
        'contested': {'meals': meals_seen, 'share': contested / meals_seen if meals_seen else None},
        # blocks more than half a metre from where they started, per arena at its end
        'blocks_moved': summary((moved > 0.5).sum(1)[:, None]),
    }


def score(cfg: Config, policy: str | None = None, brain: Path | str | None = None, mode: str = 'drawn',
          episodes: int = EPISODES, seed: int = SEED, device: str = 'cpu', threads: int = 1) -> dict:
    """One eval, of a scripted policy by name or of a brain in one of MODES."""
    torch.set_num_threads(threads)
    make = brain_policy(brain, mode, device) if brain else POLICIES[policy or 'random']
    return run(cfg, make, episodes, seed)


def side_by_side(cfg: Config, jobs: dict[str, dict], episodes: int = EPISODES, seed: int = SEED,
                 device: str = 'cpu') -> dict:
    """score() for each of jobs (name → its policy or brain and mode), each in its own process."""
    threads = max(1, (cpu_quota() or torch.get_num_threads()) // len(jobs))
    # spawn, not fork: a forked child of a process holding CUDA can hang
    with ProcessPoolExecutor(len(jobs), mp_context=mp.get_context('spawn')) as pool:
        running = {name: pool.submit(score, cfg, episodes=episodes, seed=seed, device=device, threads=threads, **job)
                   for name, job in jobs.items()}
        return {name: f.result() for name, f in running.items()}


def summary(x: np.ndarray) -> dict:
    """x is (arenas, creatures): the error comes from the arenas' means, and p10 is the creature a tenth of the way up."""
    arenas = x.mean(1)
    return {'mean': float(x.mean()), 'stderr': float(arenas.std(ddof=1) / np.sqrt(len(arenas))) if len(arenas) > 1 else 0.0,
            'p10': float(np.percentile(x, 10)), 'min': float(x.min()), 'max': float(x.max())}


def beats(brain: dict, baseline: dict) -> list[str]:
    """Why brain doesn't clearly beat baseline (docs/evals.md), or nothing if it does."""
    why = []
    food, base = brain['food_per_minute']['mean'], baseline['food_per_minute']['mean']
    if food < 2 * base:
        why.append(f'food/min {food:.2f} is under twice {base:.2f}')
    for m in ('food_per_minute', 'seconds_alive'):
        b, r = brain[m], baseline[m]
        gap, err = b['mean'] - r['mean'], np.hypot(b['stderr'], r['stderr'])
        if gap <= 3 * err:
            why.append(f'{m} is ahead by {gap:.2f}, not more than three standard errors ({3 * err:.2f})')
    return why


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', nargs='*', choices=sorted(POLICIES), default=['random'], help='none with --policy alone, to score only brains')
    parser.add_argument('--config', default=str(DEFAULT))
    parser.add_argument('--brain', nargs='*', default=[], help='checkpoints to score alongside the policies')
    parser.add_argument('--modes', nargs='+', choices=MODES, default=['drawn'], help='how each brain picks its actions')
    parser.add_argument('--held-out', action='store_true', help=f'the promotion worlds (seed {HELD_OUT}) instead of {SEED}')
    parser.add_argument('--episodes', type=int, default=EPISODES)
    parser.add_argument('--device', default='cpu', help="where the brains run; the worlds are always on the CPU")
    parser.add_argument('--out', help='write the results here as JSON')
    args = parser.parse_args()
    cfg = load(args.config)
    seed = HELD_OUT if args.held_out else SEED

    jobs: dict[str, dict] = {name: {'policy': name} for name in args.policy}
    for b in args.brain:
        for mode in args.modes:
            jobs[Path(b).name + ('' if mode == 'drawn' else f' {mode}')] = {'brain': b, 'mode': mode}
    results = side_by_side(cfg, jobs, args.episodes, seed, args.device)
    print(f'{Path(args.config).name}, {args.episodes} episodes of up to {cfg.episode.seconds:g} s, seed {seed}; ± over arenas')
    width = max(8, *map(len, jobs))
    print(f'{"policy":<{width}}  {"food/min":>14}  {"seconds alive":>16}  {"p10":>5}  {"stored":>12}  {"jelly":>5}'
          f'  {"died":>5}  {"by jelly":>8}  {"colonies lost":>13}'
          + (f'  {"in dark":>7}  {"nights":>6}  {"through night 1":>15}' if cfg.night.on else '')
          + (f'  {"to the end":>10}  {"hatched":>7}  {"hatching":>9}  {"size at end":>11}  {"peak":>5}' if cfg.hatch.on else ''))
    for name, r in results.items():
        f, s, st, d = r['food_per_minute'], r['seconds_alive'], r['stored'], r['deaths']
        print(f'{name:<{width}}  {f["mean"]:7.2f} ± {f["stderr"]:4.2f}  {s["mean"]:8.1f} ± {s["stderr"]:5.1f}  {s["p10"]:5.0f}'
              f'  {st["mean"]:5.1f} ± {st["stderr"]:4.1f}  {r["jelly"]["mean"]:5.2f}  {d["died"]:5}  {d["beside_jelly"]:8}'
              f'  {d["colonies_lost"]:>6} of {d["colonies"]:<4}'
              + (f'  {d["in_dark"]:7}  {r["nights"]["mean"]:6.2f}  {r["through_first_night"] if r["through_first_night"] is not None else "–":>8} of {d["colonies"]:<4}'
                 if cfg.night.on else '')
              + (f'  {r["colonies_to_the_end"]:>3} of {d["colonies"]:<4}  {r["hatched"]["mean"]:7.2f}'
                 f'  {r["hatched"]["colonies"]:>9}  {r["colony_size"]["end"]["mean"]:11.2f}  {r["colony_size"]["peak"]["mean"]:5.2f}'
                 if cfg.hatch.on else ''))
        log.info('eval done', policy=name, food_per_minute=round(f['mean'], 3), seconds_alive=round(s['mean'], 1))
    print(f'\n{"yes on":<{width}}  ' + '  '.join(f'{k:>16}' for k in CONTEXTS) + '  ' + '  '.join(f'{"turn² " + k:>16}' for k in PLACES))
    for name, r in results.items():
        rates = [r['actions'][k]['yes'] for k in CONTEXTS]
        print(f'{name:<{width}}  ' + '  '.join(f'{"–" if y is None else f"{y:.1%}":>16}' for y in rates) + '  '
              + '  '.join(f'{"–" if t is None else f"{t:.2f}":>16}' for t in (r['turning'][k] for k in PLACES)))
    print(f'\n{"meals":<{width}}  {"away by day":>11}  {"contested":>9}  {"from middle":>11}  {"blocks moved":>12}')
    for name, r in results.items():
        share = r['contested']['share']
        print(f'{name:<{width}}  {r["deaths"]["away_by_day"]:11}  {"–" if share is None else f"{share:.1%}":>9}'
              f'  {r["from_middle"]["mean"]:11.1f}  {r["blocks_moved"]["mean"]:12.2f}')
    if args.out:
        Path(args.out).write_text(json.dumps({'config': Path(args.config).name, 'results': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
