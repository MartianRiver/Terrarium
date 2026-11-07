# Run one arena and write it as a replay, until the time asked for or the end
# of its episode, whichever comes first. Random actions unless given a brain.
#
#   uv run python -m terrarium.record out.jsonl.gz --seconds 30 --seed 0 [--policy greedy | --brain X.pt [--ghost READOUT]]

import argparse
from pathlib import Path

from . import replay
from .brain import brain_id
from .config import Config, load
from .evals import brain_policy, greedy_policy
from .ghost import Readout, Trail
from .log import Logger
from .random_actions import RandomActions
from .runs import commit
from .world import World

log = Logger('record')


def record(cfg: Config, path: Path | str, ticks: int, seed: int = 0, policy: str = 'random',
           brain: Path | str | None = None, ghost: Path | str | None = None) -> World:
    world = World(cfg, 1, seed)
    trail = None
    if ghost:
        readout = Readout.load(ghost)
        if not brain or readout.brain != brain_id(brain):
            raise ValueError(f'{ghost} was fitted to another brain than the one recorded')
        trail = Trail(readout, world)
    if brain:
        act = brain_policy(brain, watch=trail.watch if trail else None)(world)
        who: str | dict = {'id': brain_id(brain), 'file': Path(brain).name}
    elif policy == 'greedy':
        act, who = greedy_policy(world), 'greedy'
    else:
        actions = RandomActions(1, len(world.colony), seed)
        act, who = (lambda _: actions()), 'random'
    source = {'commit': commit(), 'seed': seed, 'brain': who}
    with replay.Writer(path, replay.header(world, 0, source)) as out:
        out.write(replay.frame(world, 0))
        for _ in range(ticks):
            world.step(act(world))
            frame = replay.frame(world, 0)
            if trail and (ghosts := trail.frame(0)):
                frame['ghosts'] = ghosts
            out.write(frame)
            if world.ended[0]:
                break
    log.info('replay written', path=str(path), frames=out.frames, bytes=Path(path).stat().st_size)
    return world


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('out')
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--config', default=None)
    parser.add_argument('--policy', choices=['random', 'greedy'], default='random')
    parser.add_argument('--brain', help='a checkpoint; steers by its mean, yes/no actions drawn')
    parser.add_argument('--ghost', help='a readout (terrarium.ghost fit) of that brain: the replay gets where its notes put the tree')
    args = parser.parse_args()
    cfg = load(args.config) if args.config else load()
    try:
        record(cfg, args.out, round(args.seconds * cfg.tick_hz), args.seed, args.policy, args.brain, args.ghost)
    except ValueError as err:
        parser.error(str(err))


if __name__ == '__main__':
    main()
