# Train a brain with PPO and keep a run record of it (runs.py).
#
#   uv run python -m terrarium.train NAME --world configs/solo.toml [--parent X.pt] [--seed 0] [--scratch]
#                                         [--device cuda|mps|cpu] [--workers N] [--fast]
#
# Ends by scoring the last checkpoint on the evals next to random, three ways (evals.MODES: yes/no drawn,
# all by the mean, all drawn as in training), into the run's evals.json.

import argparse
import copy
import json
import time
from pathlib import Path
from typing import cast

import numpy as np
import torch

from . import evals, schema
from .brain import SHAPE, Brain, brain_id, save
from .brain import load as load_brain
from .config import DEFAULT, TRAIN, load, load_train
from .log import Logger
from .ppo import advantages, update
from .rollouts import Collector
from .runs import ROOT, Run, cpu_quota

log = Logger('train')


def best_device() -> str:
    if torch.cuda.is_available():
        return 'cuda'
    return 'mps' if torch.backends.mps.is_available() else 'cpu'


def train(name: str, world_path: Path | str, train_path: Path | str = TRAIN, parent: Path | str | None = None,
          seed: int = 0, scratch: bool = False, root: Path = ROOT, device: str | None = None,
          workers: int = 1, score: bool = True, mix: list[tuple[Path | str, int]] | None = None,
          fast: bool = False) -> Run:
    world_cfg, cfg = load(world_path), load_train(train_path)
    mixed = [(Path(w), load(w), n) for w, n in (mix or [])]
    ppo = cfg.ppo
    device = device or best_device()
    if not 1 <= workers <= ppo.arenas:
        raise ValueError(f'{workers} workers for {ppo.arenas} arenas; it takes at least one arena each')
    if (quota := cpu_quota()) and quota < torch.get_num_threads():
        torch.set_num_threads(quota)
    torch.manual_seed(seed)
    if parent:
        learner, made = load_brain(parent)
        # the checkpoint's own meta names the run (and samples) it came from, wherever the file was copied to
        parent_record = {'file': str(parent), 'id': brain_id(parent), 'meta': made}
    else:
        learner, parent_record = Brain(**SHAPE), None
    learner.restart(cfg.start.fresh)
    run = Run(name, {
        'world': {'file': Path(world_path).name, 'config': world_cfg.to_dict()},
        'mix': [{'file': w.name, 'arenas': n, 'config': c.to_dict()} for w, c, n in mixed],
        'train': {'file': Path(train_path).name, 'config': cfg.to_dict()},
        'parent': parent_record, 'schema': schema.current(), 'shape': learner.shape, 'seed': seed,
        'device': device, 'gpu': torch.cuda.get_device_name() if device == 'cuda' else None,
        'workers': workers, 'threads': torch.get_num_threads(), 'fast': fast,
    }, scratch=scratch, root=root)

    learner.to(device)
    optimizer = torch.optim.Adam(learner.parameters(), lr=ppo.lr, eps=1e-5)
    # the same weights, compiled for the update; minibatch sizes change with how many are alive, hence dynamic
    model = cast(Brain, torch.compile(learner, dynamic=True)) if fast else learner
    rollouts = Collector(world_cfg, cfg, ppo.arenas, seed, copy.deepcopy(learner).cpu(), workers,
                         [(c, n) for _, c, n in mixed])
    per_update = rollouts.samples * ppo.steps
    updates = max(1, ppo.samples // per_update)
    meta = {'run': run.id, 'commit': run.record['commit'], 'scratch': scratch,
            'parent': parent_record and parent_record['id'], 'repeat': ppo.repeat}
    log.info('training', run=run.id, updates=updates, per_update=per_update, device=device, workers=workers)

    started = time.perf_counter()
    checkpoint = None
    for u in range(1, updates + 1):
        for group in optimizer.param_groups:
            group['lr'] = ppo.lr * (1 - (u - 1) / updates) if ppo.anneal else ppo.lr
        tick = time.perf_counter()
        roll, last_value = rollouts.collect({k: v.cpu() for k, v in learner.state_dict().items()}, ppo.steps)
        adv, returns = advantages(roll.rewards, roll.values, roll.dones, last_value, ppo.gamma, ppo.lam)
        collected = time.perf_counter()
        stats = update(model, optimizer, roll, adv, returns, ppo, bf16=fast)
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
    if not score:
        run.finish(samples=updates * per_update, checkpoint=checkpoint.name, brain=brain_id(checkpoint))
        return run
    scores = {'random': evals.run(world_cfg, evals.random_policy),
              'brain': evals.run(world_cfg, evals.brain_policy(checkpoint)),
              'mean': evals.run(world_cfg, evals.brain_policy(checkpoint, 'mean')),
              'sampled': evals.run(world_cfg, evals.brain_policy(checkpoint, 'sampled'))}
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
    parser.add_argument('--mix', nargs='*', default=[], metavar='WORLD:ARENAS',
                        help='arenas of other worlds to train in beside --world, e.g. configs/solo.toml:64')
    parser.add_argument('--fast', action='store_true', help='compile the update and run its forward pass in bfloat16 (CUDA)')
    parser.add_argument('--no-evals', action='store_true', help="skip the evals at the end (when something else scores the run)")
    args = parser.parse_args()
    train(args.name, args.world, args.train, args.parent, args.seed, args.scratch, device=args.device,
          workers=args.workers, score=not args.no_evals, fast=args.fast,
          mix=[(w, int(n)) for w, n in (m.rsplit(':', 1) for m in args.mix)])


if __name__ == '__main__':
    main()
