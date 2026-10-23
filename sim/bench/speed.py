# The sim's speed with random actions, for 1, 16 and 64 arenas, without and
# with everyone looking: the numbers each stage is held to (docs/benchmark.md).
#
#   uv run python bench/speed.py [--config configs/solo.toml]

import argparse
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import pymunk

from terrarium import World, load
from terrarium.config import DEFAULT
from terrarium.random_actions import RandomActions
from terrarium.vision import look


def rate(cfg, arenas, seconds, vision):
    world = World(cfg, arenas, seed=arenas)
    act = RandomActions(arenas, len(world.colony), seed=arenas)
    for _ in range(20):
        world.step(act())
    ticks, start = 0, time.perf_counter()
    while (elapsed := time.perf_counter() - start) < seconds:
        for _ in range(10):
            world.step(act())
            if vision:
                look(world)
            # the bench runs longer than an episode, and a reset is part of the cost
            world.reset(world.ended)
        ticks += 10
    return ticks / elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arenas', type=int, nargs='+', default=[1, 16, 64])
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--config', default=str(DEFAULT))
    args = parser.parse_args()

    cfg = load(args.config)
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True).stdout.strip()
    print(f'{commit}{" (uncommitted changes)" if dirty else ""}  {platform.machine()}  python {platform.python_version()}'
          f'  numpy {np.__version__}  pymunk {pymunk.version}')
    v = cfg.vision
    print(f'{Path(args.config).name}: {len(cfg.block)} blocks, {cfg.colonies.count * cfg.colonies.size} creatures,'
          f' {cfg.food.count} food, {cfg.substeps} substeps, {v.rays} rays to {v.range} m')
    print('arenas  ticks/s  arena-ticks/s  with vision: ticks/s  arena-ticks/s')
    for arenas in args.arenas:
        r, seen = rate(cfg, arenas, args.seconds, False), rate(cfg, arenas, args.seconds, True)
        print(f'{arenas:>6}  {r:7.0f}  {r * arenas:13.0f}  {seen:20.0f}  {seen * arenas:13.0f}')


if __name__ == '__main__':
    main()
