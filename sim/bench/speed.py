# The sim's speed with random actions, for 1, 16 and 64 arenas: the number
# each stage is held to (docs/benchmark.md).
#
#   uv run python bench/speed.py

import argparse
import platform
import subprocess
import time

import numpy as np
import pymunk

from terrarium import World, load
from terrarium.random_actions import RandomActions


def rate(cfg, arenas, seconds):
    world = World(cfg, arenas, seed=arenas)
    act = RandomActions(arenas, len(world.colony), seed=arenas)
    for _ in range(20):
        world.step(act())
    ticks, start = 0, time.perf_counter()
    while (elapsed := time.perf_counter() - start) < seconds:
        for _ in range(10):
            world.step(act())
        ticks += 10
    return ticks / elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arenas', type=int, nargs='+', default=[1, 16, 64])
    parser.add_argument('--seconds', type=float, default=5)
    args = parser.parse_args()

    cfg = load()
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True).stdout.strip()
    print(f'{commit}{" (uncommitted changes)" if dirty else ""}  {platform.machine()}  python {platform.python_version()}'
          f'  numpy {np.__version__}  pymunk {pymunk.version}')
    print(f'{len(cfg.block)} blocks, {cfg.colonies.count * cfg.colonies.size} creatures, {cfg.food.count} food,'
          f' {cfg.substeps} substeps')
    print('arenas  ticks/s  arena-ticks/s')
    for arenas in args.arenas:
        r = rate(cfg, arenas, args.seconds)
        print(f'{arenas:>6}  {r:7.0f}  {r * arenas:13.0f}')


if __name__ == '__main__':
    main()
