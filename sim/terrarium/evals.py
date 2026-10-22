# Evals v1: a policy plays a fixed set of episodes on fixed seeds, one per
# arena, and gets two numbers: food per minute and time alive. Random actions
# are the baseline every brain has to beat; greedy is a scripted forager that
# heads for the nearest food it can see, there to show what the senses allow.
#
#   uv run python -m terrarium.evals --policy random greedy --config configs/solo.toml [--brain X.pt]

import argparse
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .brain import load as load_brain
from .config import DEFAULT, Config, load
from .forage import observe
from .log import Logger
from .random_actions import RandomActions
from .vision import FOOD, NOTHING, look
from .world import World

log = Logger('evals')

# far from any seed training uses, so a brain is never scored on worlds it trained on
SEED = 1_000_000
EPISODES = 64

Policy = Callable[[World], np.ndarray]


def random_policy(world: World) -> Policy:
    act = RandomActions(world.arenas, len(world.colony), SEED)
    return lambda _: act()


def greedy_policy(world: World) -> Policy:
    v = world.cfg.vision
    angles = np.linspace(-v.fov / 2, v.fov / 2, v.rays)
    ahead = np.abs(angles) < 0.5

    def act(w: World) -> np.ndarray:
        dist, kind = look(w)
        food = np.where(kind == FOOD, dist, np.inf)
        nearest = food.argmin(-1)
        sees = np.isfinite(food.min(-1))
        # nothing to eat in view: go straight, and turn hard when something's close ahead
        blocked = (np.where(ahead & (kind != NOTHING), dist, np.inf).min(-1) < 1.5)
        turn = np.where(sees, np.clip(angles[nearest] * 3, -1, 1), np.where(blocked, 1.0, 0.0))
        return np.stack([np.ones_like(turn), turn], -1)
    return act


POLICIES = {'random': random_policy, 'greedy': greedy_policy}


def brain_policy(path: Path | str) -> Callable[[World], Policy]:
    """A trained brain, taking its mean action: evals score what it's learned, not its exploration."""
    brain, _ = load_brain(path)
    brain.eval()

    def make(world: World) -> Policy:
        last = np.zeros((world.arenas, len(world.colony), 2))

        def act(w: World) -> np.ndarray:
            nonlocal last
            last = np.clip(brain.act(observe(w, last), sample=False), -1, 1).reshape(last.shape)
            return last
        return act
    return make


def run(cfg: Config, make: Callable[[World], Policy], episodes: int = EPISODES) -> dict:
    """Every episode to its end. Returns per-creature food per minute and seconds alive, with their means and errors."""
    world = World(cfg, episodes, SEED)
    policy = make(world)
    lived = np.zeros(world.alive.shape, int)
    meals = np.zeros(world.alive.shape, int)
    done = np.zeros(episodes, bool)
    while not done.all():
        before = world.alive & ~done[:, None]
        world.step(policy(world))
        lived += before
        # an arena that has ended stops counting; the others carry on
        finished = world.ended & ~done
        meals[finished] = world.meals[finished]
        done |= finished
    alive = lived / cfg.tick_hz
    per_minute = meals / (alive / 60)
    return {
        'episodes': episodes, 'seed': SEED,
        'food_per_minute': summary(per_minute), 'seconds_alive': summary(alive),
        'food': summary(meals),
    }


def summary(x: np.ndarray) -> dict:
    x = x.ravel()
    return {'mean': float(x.mean()), 'stderr': float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0,
            'min': float(x.min()), 'max': float(x.max())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', nargs='+', choices=sorted(POLICIES), default=['random'])
    parser.add_argument('--config', default=str(DEFAULT))
    parser.add_argument('--brain', nargs='*', default=[], help='checkpoints to score alongside the policies')
    parser.add_argument('--episodes', type=int, default=EPISODES)
    parser.add_argument('--out', help='write the results here as JSON')
    args = parser.parse_args()
    cfg = load(args.config)

    results = {}
    print(f'{Path(args.config).name}, {args.episodes} episodes of up to {cfg.episode.seconds:g} s, seed {SEED}')
    width = max(8, *(len(Path(b).name) for b in args.brain))
    print(f'{"policy":<{width}}  {"food/min":>14}  {"seconds alive":>16}')
    makers = {name: POLICIES[name] for name in args.policy} | {Path(b).name: brain_policy(b) for b in args.brain}
    for name, make in makers.items():
        r = results[name] = run(cfg, make, args.episodes)
        f, s = r['food_per_minute'], r['seconds_alive']
        print(f'{name:<{width}}  {f["mean"]:7.2f} ± {f["stderr"]:4.2f}  {s["mean"]:8.1f} ± {s["stderr"]:5.1f}')
        log.info('eval done', policy=name, food_per_minute=round(f['mean'], 3), seconds_alive=round(s['mean'], 1))
    if args.out:
        Path(args.out).write_text(json.dumps({'config': Path(args.config).name, 'results': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
