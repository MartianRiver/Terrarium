# Head to head: a different policy or brain in each colony of the same arenas,
# racing each other for the same food. Seats aren't equal (each nest has its
# own run to the patches), so every one takes every seat in turn, over the same
# episodes, and its numbers are added up over its seats.
#
#   uv run python -m terrarium.versus --config configs/colony.toml --held-out nester A.pt B.pt [--out FILE]

import argparse
import json
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable

import numpy as np
import torch

from .config import Config, load
from .evals import EPISODES, HELD_OUT, POLICIES, SEED, Policy, brain_policy, run
from .runs import cpu_quota
from .world import World


def maker(entry: str, mode: str = 'drawn', device: str = 'cpu') -> Callable[[World], Policy]:
    return POLICIES[entry] if entry in POLICIES else brain_policy(entry, mode, device)


def mixed(makers: list[Callable[[World], Policy]]) -> Callable[[World], Policy]:
    """Colony c plays by makers[c]. Each sees the whole world, as it would on its own."""
    def make(world: World) -> Policy:
        policies = [m(world) for m in makers]

        def act(w: World) -> np.ndarray:
            actions = [p(w) for p in policies]
            # scripted policies may have fewer actions than a brain: the ones they lack are no
            out = np.full((*actions[0].shape[:2], max(a.shape[-1] for a in actions)), -1.0)
            out[..., :2] = 0
            for c, a in enumerate(actions):
                mine = w.colony == c
                out[:, mine, :a.shape[-1]] = a[:, mine]
            return out
        return act
    return make


def seat(cfg: Config, entries: list[str], turn: int, episodes: int, seed: int, mode: str, device: str,
         threads: int) -> dict:
    """One turn: colony c is played by entries[(c + turn) % n]."""
    torch.set_num_threads(threads)
    order = [entries[(c + turn) % len(entries)] for c in range(len(entries))]
    return {'order': order, **run(cfg, mixed([maker(e, mode, device) for e in order]), episodes, seed)['per_colony']}


def versus(cfg: Config, entries: list[str], episodes: int = EPISODES, seed: int = SEED, mode: str = 'drawn',
           device: str = 'cpu') -> dict:
    if len(entries) != cfg.colonies.count:
        raise ValueError(f'{len(entries)} entries for {cfg.colonies.count} colonies')
    threads = max(1, (cpu_quota() or torch.get_num_threads()) // len(entries))
    with ProcessPoolExecutor(len(entries), mp_context=mp.get_context('spawn')) as pool:
        turns = list(pool.map(seat, *zip(*[(cfg, entries, t, episodes, seed, mode, device, threads)
                                           for t in range(len(entries))])))
    out = {}
    for entry in dict.fromkeys(entries):
        seats = [(t, c) for t in turns for c, e in enumerate(t['order']) if e == entry]
        mean = lambda k: float(np.mean([t[k][c] for t, c in seats]))
        out[entry] = {'colonies': episodes * len(seats),
                      'to_the_end': sum(t['to_the_end'][c] for t, c in seats),
                      'lost': sum(t['lost'][c] for t, c in seats),
                      'size_end': mean('size_end'), 'hatched': mean('hatched'), 'alive': mean('alive')}
    return {'episodes': episodes, 'seed': seed, 'mode': mode, 'turns': turns, 'entries': out}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('entries', nargs='+', help=f'one per colony: a policy ({", ".join(POLICIES)}) or a checkpoint')
    parser.add_argument('--config', required=True)
    parser.add_argument('--held-out', action='store_true', help=f'the promotion worlds (seed {HELD_OUT})')
    parser.add_argument('--episodes', type=int, default=EPISODES)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--out', help='write the results here as JSON')
    args = parser.parse_args()
    cfg = load(args.config)
    result = versus(cfg, args.entries, args.episodes, HELD_OUT if args.held_out else SEED, device=args.device)
    print(f'{Path(args.config).name}, {args.episodes} episodes a seat, every entry in every seat')
    width = max(8, *map(len, result['entries']))
    print(f'{"entry":<{width}}  {"to the end":>14}  {"lost":>5}  {"size at end":>11}  {"hatched":>7}  {"alive (s)":>9}')
    for name, r in result['entries'].items():
        print(f'{name:<{width}}  {r["to_the_end"]:>5} of {r["colonies"]:<5}  {r["lost"]:>5}  {r["size_end"]:11.2f}'
              f'  {r["hatched"]:7.2f}  {r["alive"]:9.1f}')
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1) + '\n')


if __name__ == '__main__':
    main()
