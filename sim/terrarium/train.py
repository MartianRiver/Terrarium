# Train a brain with PPO and keep a run record of it (runs.py).
#
#   uv run python -m terrarium.train NAME --world configs/solo.toml [--parent X.pt] [--seed 0] [--scratch]
#                                         [--device cuda|mps|cpu] [--workers N]
#
# Ends by scoring the last checkpoint on the evals next to random, into the run's evals.json.

import argparse
import copy
import json
import time
from pathlib import Path

import numpy as np
import torch

from . import evals, schema
from .brain import SHAPE, Brain, brain_id, save
from .brain import load as load_brain
from .config import DEFAULT, TRAIN, load, load_train
from .log import Logger
from .ppo import advantages, update
from .rollouts import Collector
from .runs import ROOT, Run

log = Logger('train')


def best_device() -> str:
    if torch.cuda.is_available():
        return 'cuda'
    return 'mps' if torch.backends.mps.is_available() else 'cpu'


def train(name: str, world_path: Path | str, train_path: Path | str = TRAIN, parent: Path | str | None = None,
          seed: int = 0, scratch: bool = False, root: Path = ROOT, device: str | None = None,
          workers: int = 1) -> Run:
    world_cfg, cfg = load(world_path), load_train(train_path)
    ppo = cfg.ppo
    device = device or best_device()
    if not 1 <= workers <= ppo.arenas:
        raise ValueError(f'{workers} workers for {ppo.arenas} arenas; it takes at least one arena each')
    torch.manual_seed(seed)
    if parent:
        learner, _ = load_brain(parent)
        parent_record = {'file': str(parent), 'id': brain_id(parent)}
    else:
        learner, parent_record = Brain(**SHAPE), None
    run = Run(name, {
        'world': {'file': Path(world_path).name, 'config': world_cfg.to_dict()},
        'train': {'file': Path(train_path).name, 'config': cfg.to_dict()},
        'parent': parent_record, 'schema': schema.current(), 'shape': learner.shape, 'seed': seed,
        'device': device, 'workers': workers,
    }, scratch=scratch, root=root)

    learner.to(device)
    optimizer = torch.optim.Adam(learner.parameters(), lr=ppo.lr, eps=1e-5)
    rollouts = Collector(world_cfg, cfg.reward, ppo.arenas, seed, copy.deepcopy(learner).cpu(), workers)
    per_update = rollouts.samples * ppo.steps
    updates = max(1, ppo.samples // per_update)
    meta = {'run': run.id, 'commit': run.record['commit'], 'scratch': scratch,
            'parent': parent_record and parent_record['id']}
    log.info('training', run=run.id, updates=updates, per_update=per_update, device=device, workers=workers)

    started = time.perf_counter()
    checkpoint = None
    for u in range(1, updates + 1):
        for group in optimizer.param_groups:
            group['lr'] = ppo.lr * (1 - (u - 1) / updates)
        tick = time.perf_counter()
        roll, last_value = rollouts.collect({k: v.cpu() for k, v in learner.state_dict().items()}, ppo.steps)
        adv, returns = advantages(roll.rewards, roll.values, roll.dones, last_value, ppo.gamma, ppo.lam)
        collected = time.perf_counter()
        stats = update(learner, optimizer, roll, adv, returns, ppo)
        done = time.perf_counter()

        row = {'update': u, 'samples': u * per_update, 'seconds': round(done - started, 1),
               'samples_per_second': round(per_update / (done - tick)),
               'collect_seconds': round(collected - tick, 2), 'update_seconds': round(done - collected, 2),
               'reward_per_sample': float(roll.rewards.mean()), **rollouts.episodes.take(), **stats}
        run.log_metrics(row)
        if u == 1 or u % 10 == 0 or u == updates:
            log.info('update', u=u, of=updates, sps=row['samples_per_second'],
                     ret=round(row.get('episode_return', np.nan), 2), lived=round(row.get('episode_seconds', np.nan), 1),
                     kl=round(stats['kl'], 4))
        if u % ppo.checkpoint_every == 0 or u == updates:
            checkpoint = run.dir / 'checkpoints' / f'{u * per_update:011d}.pt'
            save(learner, checkpoint, **meta, samples=u * per_update)

    rollouts.close()
    assert checkpoint is not None
    scores = {'random': evals.run(world_cfg, evals.random_policy),
              'brain': evals.run(world_cfg, evals.brain_policy(checkpoint))}
    (run.dir / 'evals.json').write_text(json.dumps({'checkpoint': checkpoint.name, **scores}, indent=2) + '\n')
    run.finish(samples=updates * per_update, checkpoint=checkpoint.name, brain=brain_id(checkpoint),
               evals={k: {m: round(v[m]['mean'], 3) for m in ('food_per_minute', 'seconds_alive')}
                      for k, v in scores.items()})
    return run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='a few words for the folder name, e.g. solo-first')
    parser.add_argument('--world', default=str(DEFAULT))
    parser.add_argument('--train', default=str(TRAIN))
    parser.add_argument('--parent', help='a checkpoint to carry on from')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--scratch', action='store_true', help='allow uncommitted changes; the run can never be promoted')
    parser.add_argument('--device', choices=['cuda', 'mps', 'cpu'], help='where the update runs (default: the best there is)')
    parser.add_argument('--workers', type=int, default=1, help='processes playing rollouts; the arenas are split between them')
    args = parser.parse_args()
    train(args.name, args.world, args.train, args.parent, args.seed, args.scratch, device=args.device,
          workers=args.workers)


if __name__ == '__main__':
    main()
