# Runs both physics candidates on the same scene and the same random actions:
# speed at 1/16/64 arenas, ray vision cost, and how well each keeps things apart.
#
#   uv run python bench/physics_choice.py

import argparse
import platform
import time

import numpy as np

import rays
from engine_world import EngineWorld
from scene import BLOCKS, CREATURES, HALF, RADIUS, Food, RandomActions
from vector_world import VectorWorld, rotate

HALVES = np.array([(w / 2, h / 2) for w, h, _ in BLOCKS])
CANDIDATES = {'numpy': VectorWorld, 'pymunk': EngineWorld}


def timed(fn, ticks):
    start = time.perf_counter()
    for _ in range(ticks):
        fn()
    return ticks / (time.perf_counter() - start)


def speed(name, arenas, ticks):
    world = CANDIDATES[name](arenas, seed=arenas)
    act = RandomActions(arenas, seed=arenas)
    for _ in range(20):
        world.step(act())
    return timed(lambda: world.step(act()), ticks)


def ray_speed(arenas, ticks, native=False):
    world = EngineWorld(arenas, seed=arenas, food_shapes=native)
    act, food = RandomActions(arenas, arenas), Food(arenas, arenas)
    for _ in range(40):
        world.step(act())
    if native:
        world.sync_food(food.pos, np.ones(food.alive.shape, bool))
        dirs = rays.directions(world.heading)
        return timed(lambda: world.cast_rays(dirs), ticks)
    return timed(lambda: rays.cast(world.pos, world.heading, food.pos, food.alive, world.bpos, world.bang, HALVES), ticks)


def overlaps(pos, bpos, bang):
    """Worst creature/creature overlap, creature/block overlap and block corner past a wall, in metres."""
    d = pos[:, :, None] - pos[:, None]
    dist = np.sqrt((d * d).sum(-1)) + np.eye(CREATURES) * 1e9
    cc = np.maximum(2 * RADIUS - dist, 0).max()

    cos, sin = np.cos(bang)[:, None], np.sin(bang)[:, None]
    local = rotate(pos[:, :, None] - bpos[:, None], cos, -sin)
    outside = np.sqrt(((local - np.clip(local, -HALVES, HALVES)) ** 2).sum(-1))
    depth = np.min(HALVES - np.abs(local), -1)
    cb = np.where(outside > 0, np.maximum(RADIUS - outside, 0), RADIUS + depth).max()

    signs = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]], float)
    corners = rotate(signs * HALVES[:, None], np.cos(bang)[..., None], np.sin(bang)[..., None]) + bpos[..., None, :]
    bw = np.maximum(np.abs(corners) - HALF, 0).max()
    return cc, cb, bw


def quality(name, arenas=16, ticks=1200):
    world = CANDIDATES[name](arenas, seed=99)
    act, food = RandomActions(arenas, 99), Food(arenas, 99)
    start_b = world.state()[2].copy()
    worst = np.zeros(3)
    mean = np.zeros(3)
    turned = np.zeros((arenas, len(BLOCKS)))
    last_ang = world.state()[3].copy()
    for _ in range(ticks):
        world.step(act())
        pos, _, bpos, bang = world.state()
        food.update(pos)
        o = np.array(overlaps(pos, bpos, bang))
        worst = np.maximum(worst, o)
        mean += o / ticks
        turned += np.abs(bang - last_ang)
        last_ang = bang.copy()
    moved = np.sqrt(((world.state()[2] - start_b) ** 2).sum(-1))
    return worst, mean, moved.mean(0), turned.mean(0), food.eaten / arenas


def check_rays(arenas=4):
    """numpy rays against pymunk's own segment queries on the same world state."""
    world = EngineWorld(arenas, seed=5, food_shapes=True)
    act, food = RandomActions(arenas, 5), Food(arenas, 5)
    for _ in range(100):
        world.step(act())
    world.sync_food(food.pos, np.ones(food.alive.shape, bool))
    mine, _ = rays.cast(world.pos, world.heading, food.pos, food.alive, world.bpos, world.bang, HALVES)
    theirs = world.cast_rays(rays.directions(world.heading))
    gap = np.abs(mine - theirs)
    return float(gap.max()), float((gap > 0.001).mean())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arenas', type=int, nargs='+', default=[1, 16, 64])
    parser.add_argument('--seconds', type=float, default=3, help='rough time per measurement')
    args = parser.parse_args()

    print(f'{platform.machine()} {platform.processor() or ""} python {platform.python_version()} numpy {np.__version__}')
    print('\nphysics only, ticks/s (arena-ticks/s)')
    for name in CANDIDATES:
        cells = []
        for arenas in args.arenas:
            probe = speed(name, arenas, 20)
            rate = speed(name, arenas, max(20, int(probe * args.seconds)))
            cells.append(f'{arenas:>3}: {rate:8.0f} ({rate * arenas:8.0f})')
        print(f'  {name:7} ' + '   '.join(cells))

    print(f'\nray vision ({rays.RAYS} rays x {CREATURES} creatures), ticks/s (arena-ticks/s)')
    for label, native in (('numpy', False), ('pymunk', True)):
        cells = []
        for arenas in args.arenas:
            probe = ray_speed(arenas, 3, native)
            rate = ray_speed(arenas, max(3, int(probe * args.seconds)), native)
            cells.append(f'{arenas:>3}: {rate:8.0f} ({rate * arenas:8.0f})')
        print(f'  {label:7} ' + '   '.join(cells))

    gap, share = check_rays()
    print(f'\nrays agree: worst gap {gap:.3f} m, {share:.1%} of rays off by more than 1 mm')

    print('\nquality over 60 s x 16 arenas: worst / mean overlap (m), block travel (m), block turn (rad), food per arena')
    for name in CANDIDATES:
        worst, mean, moved, turned, eaten = quality(name)
        print(f'  {name:7} creature/creature {worst[0]:.3f} / {mean[0]:.4f}   creature/block {worst[1]:.3f} / {mean[1]:.4f}'
              f'   block past wall {worst[2]:.3f}')
        print(f'  {"":7} light block moved {moved[0]:.1f} turned {turned[0]:.1f}   heavy block moved {moved[1]:.1f}'
              f' turned {turned[1]:.1f}   food {eaten:.0f}')


if __name__ == '__main__':
    main()
