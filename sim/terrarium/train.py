# Train a brain with PPO and keep a run record of it (runs.py).
#
#   uv run python -m terrarium.train NAME --world configs/solo.toml [--parent X.pt] [--seed 0] [--scratch]
#                                         [--device cuda|mps|cpu] [--workers N] [--fast] [--gpu-collect]
#                                         [--rivals B.pt C.pt [--rival-lr 5e-5 1e-4] [--fixed-seats]] [--memory 128 [--recall 0.1]]
#                                         [--pool 10]
#
# --memory N gives the brain N notes of memory if it has none (brain.py); it acts as before until trained, unless
# --recall starts it reading them a little (in a toy test of a 6 s wait, 0.1 learned it in
# 1.6M samples and 0 hadn't in 2.5M).
#
# With rivals, each colony is played by one of the brains (the parent's first), every brain taking every seat over
# the arenas (rollouts.seats), and each learns only from its own colonies' samples. --fixed-seats keeps colony k on
# brain k instead, for a game whose sides differ (hide-and-seek: the parent hides, the rival seeks). Their checkpoints
# go in rivals/<k>/; metrics ending _k are brain k's.
#
# --pool N plays the brain against its own past instead: one rival that doesn't learn, a copy of the parent at first,
# then at every checkpoint one of the last N checkpoints drawn at random (the parent among them until it's pushed
# out), so self-play can't settle into what only works against itself. Metric `opponent` is the samples it had.
#
# Ends by scoring the last checkpoint on the evals next to random, three ways (evals.MODES: yes/no drawn,
# all by the mean, all drawn as in training), into the run's evals.json.

import argparse
import copy
import json
import time
from collections import deque
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
from .ppo import Closure, Parts, Side, advantages, update
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
          rival_lr: list[float] | None = None, memory: int = 0, recall: float = 0.0, fixed_seats: bool = False,
          pool: int = 0) -> Run:
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
        learner = learner.with_memory(memory, recall)
    rivals = rivals or []
    if pool and rivals:
        raise ValueError('--pool plays the brain against its own past, not against --rivals')
    if (rivals or pool) and not gpu_collect:
        raise ValueError('rivals play with --gpu-collect only')
    if rival_lr and len(rival_lr) != len(rivals):
        raise ValueError(f'{len(rival_lr)} learning rates for {len(rivals)} rivals')
    loaded = [load_brain(r) for r in rivals]
    brains = [learner] + [b for b, _ in loaded] + [copy.deepcopy(learner) for _ in range(bool(pool))]
    rates = [ppo.lr] + (rival_lr or [ppo.lr] * len(rivals)) + [0.0] * bool(pool)
    for b in brains:
        b.restart(cfg.start.fresh)
    # (samples, weights) of the checkpoints the pool's opponent is drawn from
    past = [(0, copy.deepcopy(learner.state_dict()))] if pool else []
    draw = np.random.default_rng(seed)
    run = Run(name, {
        'world': {'file': Path(world_path).name, 'config': world_cfg.to_dict()},
        'mix': [{'file': w.name, 'arenas': n, 'config': c.to_dict()} for w, c, n in mixed],
        'train': {'file': Path(train_path).name, 'config': cfg.to_dict()},
        'parent': parent_record, 'schema': schema.current(), 'shape': learner.shape, 'seed': seed,
        'device': device, 'gpu': torch.cuda.get_device_name() if device == 'cuda' else None,
        'workers': workers, 'threads': torch.get_num_threads(), 'fast': fast, 'gpu_collect': gpu_collect,
        'recall': recall if memory else None, 'fixed_seats': fixed_seats if rivals else None, 'pool': pool or None,
        'rivals': [{'file': str(r), 'id': brain_id(r), 'meta': m, 'shape': b.shape, 'lr': lr}
                   for r, (b, m), lr in zip(rivals, loaded, rates[1:])],
    }, scratch=scratch, root=root)

    for b in brains:
        b.to(device)
    optimizers = [torch.optim.Adam(b.parameters(), lr=lr, eps=1e-5) for b, lr in zip(brains, rates)]
    side = None
    if ppo.side:
        if not learner.memory:
            raise ValueError('[ppo] side is a job for memory: train with --memory')
        side = Side(learner.memory, learner.shape['width'], ppo.side_back).to(device)
        optimizers[0].add_param_group({'params': list(side.parameters())})
    closure = None
    if ppo.closure:
        if not learner.memory or not world_cfg.arena.maze:
            raise ValueError('[ppo] closure is a job for memory in a maze: train with --memory in a maze world')
        closure = Closure(learner.memory).to(device)
        optimizers[0].add_param_group({'params': list(closure.parameters())})
    # the same weights, compiled for the update; minibatch sizes change with how many are alive, hence dynamic
    models = [cast(Brain, torch.compile(b, dynamic=True)) if fast and not b.memory else b for b in brains]
    parts = Parts.compiled(learner) if fast and learner.memory else None
    worlds = [(c, n) for _, c, n in mixed]
    if gpu_collect:
        actors = [copy.deepcopy(b) for b in brains]
        rollouts = OnDevice(world_cfg, cfg, ppo.arenas, seed, actors if len(brains) > 1 else actors[0], workers, worlds,
                            device, fixed_seats)
    else:
        rollouts = Collector(world_cfg, cfg, ppo.arenas, seed, copy.deepcopy(learner).cpu(), workers, worlds)
    per_update = rollouts.samples * ppo.steps
    updates = max(1, ppo.samples // per_update)
    meta = {'run': run.id, 'commit': run.record['commit'], 'scratch': scratch,
            'parent': parent_record and parent_record['id'], 'repeat': ppo.repeat}
    metas = [meta] + [{**meta, 'parent': brain_id(r), 'rival': k} for k, r in enumerate(rivals, 1)]
    log.info('training', run=run.id, updates=updates, per_update=per_update, device=device, workers=workers)

    # the brain it starts as (untrained, or the parent), so a viewer can show how it learned from the start
    save(learner, run.dir / 'checkpoints' / f'{0:011d}.pt', **meta, samples=0)
    sampler = Sampler(device).start()
    started = time.perf_counter()
    checkpoint = None
    # samples count every place in every arena, the dead and unborn included; these are the ones that trained
    live = 0
    rewarded = gave_up = stuck = False
    lived = deque(maxlen=10)
    opponent = 0
    for u in range(1, updates + 1):
        ramp = min(1.0, u / ppo.warmup) if ppo.warmup else 1.0
        for optimizer, lr in zip(optimizers, rates):
            for group in optimizer.param_groups:
                group['lr'] = (lr * (1 - (u - 1) / updates) if ppo.anneal else lr) * ramp
        tick = time.perf_counter()
        sampler.into('collect')
        roll, last_value = rollouts.collect([b.state_dict() for b in brains] if len(brains) > 1 else learner.state_dict(),
                                            ppo.steps)
        adv, returns = advantages(roll.rewards, roll.values, roll.dones, last_value, ppo.gamma, ppo.lam)
        collected = time.perf_counter()
        sampler.into('update')
        if len(brains) > 1:
            stats = {'opponent': opponent} if pool else {}
            assert isinstance(rollouts, OnDevice)
            for k, (model, optimizer) in enumerate(zip(models, optimizers)):
                if not rates[k]:
                    stats |= {f'{key}_{k}': v for key, v in rollouts.by_brain[k].take().items()}
                    continue
                own = replace(roll, active=roll.active & (rollouts.whose == k))
                got = update(model, optimizer, own, adv, returns, ppo, bf16=fast)
                if k == 0:
                    stats |= got
                stats |= {f'{key}_{k}': v for key, v in (got | rollouts.by_brain[k].take()).items()}
        else:
            stats = update(models[0], optimizers[0], roll, adv, returns, ppo, bf16=fast, side=side, closure=closure,
                           parts=parts)
        done = time.perf_counter()
        sampler.into(None)
        live += int(roll.active.sum())
        rewarded = rewarded or bool((roll.rewards != 0).any())
        gave_up = ppo.give_up > 0 and u == ppo.give_up and not rewarded

        row = {'update': u, 'samples': u * per_update, 'live_samples': live,
               'live_share': round(float(roll.active.mean()), 3), 'seconds': round(done - started, 1),
               'samples_per_second': round(per_update / (done - tick)),
               'collect_seconds': round(collected - tick, 2), 'update_seconds': round(done - collected, 2),
               'reward_per_sample': float(roll.rewards.mean()), **rollouts.episodes.take(), **stats, **sampler.take()}
        run.log_metrics(row)
        if np.isfinite(row.get('episode_seconds', np.nan)):
            lived.append(row['episode_seconds'])
        stuck = ppo.stuck > 0 and u == ppo.stuck and bool(lived) and float(np.mean(lived)) < ppo.stuck_seconds
        if u == 1 or u % 10 == 0 or u == updates:
            log.info('update', u=u, of=updates, sps=row['samples_per_second'],
                     ret=round(row.get('episode_return', np.nan), 2), lived=round(row.get('episode_seconds', np.nan), 1),
                     kl=round(stats['kl'], 4))
        if u % ppo.checkpoint_every == 0 or u == updates or gave_up or stuck:
            checkpoint = run.dir / 'checkpoints' / f'{u * per_update:011d}.pt'
            save(learner, checkpoint, **meta, samples=u * per_update)
            for k in range(1, len(rivals) + 1):
                (run.dir / 'rivals' / str(k)).mkdir(parents=True, exist_ok=True)
                save(brains[k], run.dir / 'rivals' / str(k) / checkpoint.name, **metas[k], samples=u * per_update)
            if pool:
                past = (past + [(u * per_update, copy.deepcopy(learner.state_dict()))])[-pool:]
                opponent, weights = past[draw.integers(len(past))]
                brains[1].load_state_dict(weights)
        if gave_up:
            log.warn('gave up: no reward on any update', u=u)
            break
        if stuck:
            log.warn('stuck: episodes too short', u=u, lived=round(float(np.mean(lived)), 1))
            break

    sampler.stop()
    rollouts.close()
    assert checkpoint is not None
    if gave_up or stuck:
        run.finish(samples=u * per_update, checkpoint=checkpoint.name, brain=brain_id(checkpoint),
                   **{'gave_up' if gave_up else 'stuck': u})
        return run
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
    parser.add_argument('--fixed-seats', action='store_true', help='with --rivals, colony k is always brain k')
    parser.add_argument('--pool', type=int, default=0,
                        help='play against one of the last N checkpoints of itself, drawn anew at every checkpoint')
    parser.add_argument('--memory', type=int, default=0, help='notes of memory to give a brain that has none')
    parser.add_argument('--recall', type=float, default=0.0,
                        help="with --memory, start reading the notes at this share of a fresh layer's weights (0: not at all)")
    args = parser.parse_args()
    train(args.name, args.world, args.train, args.parent, args.seed, args.scratch, device=args.device,
          workers=args.workers, score=not args.no_evals, fast=args.fast, gpu_collect=args.gpu_collect,
          mix=[(w, int(n)) for w, n in (m.rsplit(':', 1) for m in args.mix)], rivals=args.rivals,
          rival_lr=args.rival_lr, memory=args.memory, recall=args.recall, fixed_seats=args.fixed_seats,
          pool=args.pool)


if __name__ == '__main__':
    main()
