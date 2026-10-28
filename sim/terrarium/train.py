# Train a brain with PPO and keep a run record of it (runs.py).
#
#   uv run python -m terrarium.train NAME --world configs/solo.toml [--parent X.pt] [--seed 0] [--scratch]
#                                         [--device cuda|mps|cpu] [--workers N] [--fast] [--gpu-collect]
#                                         [--rivals B.pt C.pt [--rival-lr 5e-5 1e-4]] [--memory 128]
#
# --memory N gives the brain N notes of memory if it has none (brain.py); it acts as before until trained.
#
# With rivals, each colony is played by one of the brains (the parent's first), every brain taking every seat over
# the arenas (rollouts.seats), and each learns only from its own colonies' samples. Their checkpoints go in
# rivals/<k>/; metrics ending _k are brain k's.
#
# Ends by scoring the last checkpoint on the evals next to random, three ways (evals.MODES: yes/no drawn,
# all by the mean, all drawn as in training), into the run's evals.json.

import argparse
import copy
import json
import time
from dataclasses import replace
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
from .rollouts import Collector, OnDevice
from .runs import ROOT, Run, cpu_quota
from .usage import Sampler

log = Logger('train')


def best_device() -> str:
    if torch.cuda.is_available():
        return 'cuda'
    return 'mps' if torch.backends.mps.is_available() else 'cpu'


def train(name: str, world_path: Path | str, train_path: Path | str = TRAIN, parent: Path | str | None = None,
          seed: int = 0, scratch: bool = False, root: Path = ROOT, device: str | None = None,
          workers: int = 1, score: bool = True, mix: list[tuple[Path | str, int]] | None = None,
          fast: bool = False, gpu_collect: bool = False, rivals: list[Path | str] | None = None,
          rival_lr: list[float] | None = None, memory: int = 0) -> Run:
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
    if memory and learner.memory != memory:
        learner = learner.with_memory(memory)
    rivals = rivals or []
    if rivals and not gpu_collect:
        raise ValueError('rivals play with --gpu-collect only')
    if rival_lr and len(rival_lr) != len(rivals):
        raise ValueError(f'{len(rival_lr)} learning rates for {len(rivals)} rivals')
    loaded = [load_brain(r) for r in rivals]
    brains = [learner] + [b for b, _ in loaded]
    rates = [ppo.lr] + (rival_lr or [ppo.lr] * len(rivals))
    for b in brains:
        b.restart(cfg.start.fresh)
    run = Run(name, {
        'world': {'file': Path(world_path).name, 'config': world_cfg.to_dict()},
        'mix': [{'file': w.name, 'arenas': n, 'config': c.to_dict()} for w, c, n in mixed],
        'train': {'file': Path(train_path).name, 'config': cfg.to_dict()},
        'parent': parent_record, 'schema': schema.current(), 'shape': learner.shape, 'seed': seed,
        'device': device, 'gpu': torch.cuda.get_device_name() if device == 'cuda' else None,
        'workers': workers, 'threads': torch.get_num_threads(), 'fast': fast, 'gpu_collect': gpu_collect,
        'rivals': [{'file': str(r), 'id': brain_id(r), 'meta': m, 'shape': b.shape, 'lr': lr}
                   for r, (b, m), lr in zip(rivals, loaded, rates[1:])],
    }, scratch=scratch, root=root)

    for b in brains:
        b.to(device)
    optimizers = [torch.optim.Adam(b.parameters(), lr=lr, eps=1e-5) for b, lr in zip(brains, rates)]
    # the same weights, compiled for the update; minibatch sizes change with how many are alive, hence dynamic
    models = [cast(Brain, torch.compile(b, dynamic=True)) if fast else b for b in brains]
    worlds = [(c, n) for _, c, n in mixed]
    if gpu_collect:
        actors = [copy.deepcopy(b) for b in brains]
        rollouts = OnDevice(world_cfg, cfg, ppo.arenas, seed, actors if rivals else actors[0], workers, worlds, device)
    else:
        rollouts = Collector(world_cfg, cfg, ppo.arenas, seed, copy.deepcopy(learner).cpu(), workers, worlds)
    per_update = rollouts.samples * ppo.steps
    updates = max(1, ppo.samples // per_update)
    meta = {'run': run.id, 'commit': run.record['commit'], 'scratch': scratch,
            'parent': parent_record and parent_record['id'], 'repeat': ppo.repeat}
    metas = [meta] + [{**meta, 'parent': brain_id(r), 'rival': k} for k, r in enumerate(rivals, 1)]
    log.info('training', run=run.id, updates=updates, per_update=per_update, device=device, workers=workers)

    sampler = Sampler(device).start()
    started = time.perf_counter()
    checkpoint = None
    for u in range(1, updates + 1):
        for optimizer, lr in zip(optimizers, rates):
            for group in optimizer.param_groups:
                group['lr'] = lr * (1 - (u - 1) / updates) if ppo.anneal else lr
        tick = time.perf_counter()
        sampler.into('collect')
        roll, last_value = rollouts.collect([b.state_dict() for b in brains] if rivals else learner.state_dict(),
                                            ppo.steps)
        adv, returns = advantages(roll.rewards, roll.values, roll.dones, last_value, ppo.gamma, ppo.lam)
        collected = time.perf_counter()
        sampler.into('update')
        if rivals:
            stats = {}
            assert isinstance(rollouts, OnDevice)
            for k, (model, optimizer) in enumerate(zip(models, optimizers)):
                own = replace(roll, active=roll.active & (rollouts.whose == k))
                got = update(model, optimizer, own, adv, returns, ppo, bf16=fast)
                if k == 0:
                    stats |= got
                stats |= {f'{key}_{k}': v for key, v in (got | rollouts.by_brain[k].take()).items()}
        else:
            stats = update(models[0], optimizers[0], roll, adv, returns, ppo, bf16=fast)
        done = time.perf_counter()
        sampler.into(None)

        row = {'update': u, 'samples': u * per_update, 'seconds': round(done - started, 1),
               'samples_per_second': round(per_update / (done - tick)),
               'collect_seconds': round(collected - tick, 2), 'update_seconds': round(done - collected, 2),
               'reward_per_sample': float(roll.rewards.mean()), **rollouts.episodes.take(), **stats, **sampler.take()}
        run.log_metrics(row)
        if u == 1 or u % 10 == 0 or u == updates:
            log.info('update', u=u, of=updates, sps=row['samples_per_second'],
                     ret=round(row.get('episode_return', np.nan), 2), lived=round(row.get('episode_seconds', np.nan), 1),
                     kl=round(stats['kl'], 4))
        if u % ppo.checkpoint_every == 0 or u == updates:
            checkpoint = run.dir / 'checkpoints' / f'{u * per_update:011d}.pt'
            save(learner, checkpoint, **meta, samples=u * per_update)
            for k in range(1, len(brains)):
                (run.dir / 'rivals' / str(k)).mkdir(parents=True, exist_ok=True)
                save(brains[k], run.dir / 'rivals' / str(k) / checkpoint.name, **metas[k], samples=u * per_update)

    sampler.stop()
    rollouts.close()
    assert checkpoint is not None
    if not score:
        run.finish(samples=updates * per_update, checkpoint=checkpoint.name, brain=brain_id(checkpoint))
        return run
    # on a Mac they stay on the CPU, as they always have
    scores = evals.side_by_side(world_cfg, {'random': {'policy': 'random'}, 'brain': {'brain': checkpoint},
                                            'mean': {'brain': checkpoint, 'mode': 'mean'},
                                            'sampled': {'brain': checkpoint, 'mode': 'sampled'}},
                                device='cuda' if device == 'cuda' else 'cpu')
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
    parser.add_argument('--gpu-collect', action='store_true',
                        help='run the brain for rollouts once a step for every worker, on --device; workers only step the worlds')
    parser.add_argument('--no-evals', action='store_true', help="skip the evals at the end (when something else scores the run)")
    parser.add_argument('--rivals', nargs='*', default=[], metavar='BRAIN',
                        help='brains that play the other colonies and learn beside the parent (needs --gpu-collect)')
    parser.add_argument('--rival-lr', nargs='*', type=float, help="each rival's learning rate (default the train config's)")
    parser.add_argument('--memory', type=int, default=0, help='notes of memory to give a brain that has none')
    args = parser.parse_args()
    train(args.name, args.world, args.train, args.parent, args.seed, args.scratch, device=args.device,
          workers=args.workers, score=not args.no_evals, fast=args.fast, gpu_collect=args.gpu_collect,
          mix=[(w, int(n)) for w, n in (m.rsplit(':', 1) for m in args.mix)], rivals=args.rivals,
          rival_lr=args.rival_lr, memory=args.memory)


if __name__ == '__main__':
    main()
