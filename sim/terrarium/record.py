# Run one arena with random actions and write it as a replay.
#
#   uv run python -m terrarium.record out.jsonl.gz --seconds 30 --seed 0

import argparse
import subprocess
from pathlib import Path

from . import replay
from .config import Config, load
from .log import Logger
from .random_actions import RandomActions
from .world import World

log = Logger('record')


def commit() -> str:
    def git(*args):
        return subprocess.run(['git', *args], capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip()
    # dirty counts untracked files too, so a new module isn't missed
    return (git('rev-parse', '--short', 'HEAD') or 'unknown') + ('-dirty' if git('status', '--porcelain') else '')


def record(cfg: Config, path: Path | str, ticks: int, seed: int = 0) -> World:
    world = World(cfg, 1, seed)
    act = RandomActions(1, len(world.colony), seed)
    source = {'commit': commit(), 'seed': seed, 'brain': 'random'}
    with replay.Writer(path, replay.header(world, 0, source)) as out:
        out.write(replay.frame(world, 0))
        for _ in range(ticks):
            world.step(act())
            out.write(replay.frame(world, 0))
    log.info('replay written', path=str(path), frames=out.frames, bytes=Path(path).stat().st_size)
    return world


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('out')
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--config', default=None)
    args = parser.parse_args()
    cfg = load(args.config) if args.config else load()
    record(cfg, args.out, round(args.seconds * cfg.tick_hz), args.seed)


if __name__ == '__main__':
    main()
