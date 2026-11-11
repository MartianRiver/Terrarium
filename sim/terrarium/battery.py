# The skills battery: a frozen brain in each nursery skill's test world, one line a brain, so a skill that drops
# while the world still pays for it shows the same day (River, 11 Nov: "if combining things can't be done without
# them forgetting aspects of it then our brain is not good enough").
#
#   uv run python -m terrarium.battery CKPT [CKPT ...] --games 64 --seed 8121000 --out battery.json
#
# CKPT is a .pt, a run's folder or its checkpoints folder (the last checkpoint), or NAME=that. The worlds are in
# configs/battery/ (--world SKILL=PATH swaps one, e.g. the main world); --only names the skills to run. Every test is a
# frozen play: notes kept, the brain's own action noise (sampled for graze and pond, as the findings behind them were,
# drawn for the rest, as the scorer's 'kept' mode does), the same seeds for every brain.
#
#   graze     stands to graze         share of meadow time anchored (0031), the extent of a stretch
#   pond      drinks still            speed in the pond, visit length, seconds drinking a game (0030)
#   tree      jumps for apples        apples picked and brought home a minute
#   displace  goes to remembered tree the first trip to where the tree stood, kept notes minus wiped ones (0005)
#   night     stays home at night     alive at the end, still at home in the dark, nest exits a night
import argparse
import json
import re
import time
from pathlib import Path

import torch

from .battery_displace import displace
from .battery_skills import graze, night, pond, tree
from .config import load

CONFIGS = Path(__file__).resolve().parent.parent / 'configs' / 'battery'
SKILLS = {'graze': graze, 'pond': pond, 'tree': tree, 'displace': displace, 'night': night}
# the displacement test is one trip a game, so it asks for more games to say anything
DISPLACE_GAMES = 8


def find_brain(arg: str) -> tuple[str, Path]:
    name, _, spec = arg.rpartition('=')
    path = Path(spec)
    if path.is_dir():
        path = path / 'checkpoints' if (path / 'checkpoints').is_dir() else path
        path = sorted(path.glob('*.pt'))[-1]
    if not path.is_file():
        raise SystemExit(f'no checkpoint at {spec}')
    if not name:
        run = path.parent.parent.name if path.parent.name == 'checkpoints' else path.stem
        name = re.sub(r'-[0-9a-f]{12}$', '', re.sub(r'^\d{8}-\d{6}-', '', run))
    return name, path


def run_brain(path: Path, worlds: dict, skills: list[str], games: int, seed: int, displace_games: int) -> dict:
    out = {}
    for skill in skills:
        began = time.monotonic()
        cfg = load(worlds[skill])
        n = displace_games if skill == 'displace' else games
        out[skill] = {**SKILLS[skill](cfg, path, n, seed), 'seconds': round(time.monotonic() - began, 1)}
    return out


def f(x, spec='', none='-') -> str:
    return none if x is None else format(x, spec)


def line(name: str, r: dict) -> str:
    parts = [f'{name:28s}']
    for skill, fmt in LINES.items():
        if skill in r:
            parts.append(na(r[skill]) or fmt(r[skill]))
    parts.append(f"{sum(v['seconds'] for v in r.values()):.0f} s (" + ' '.join(f"{k} {v['seconds']:.0f}" for k, v in r.items()) + ')')
    return ' | '.join(parts)


def na(r: dict) -> str:
    return f"n/a ({r['na']})" if 'na' in r else ''


LINES = {
    'graze': lambda r: f"graze anchored {f(r['anchored'], '.0%')} extent {f(r['extent_m'] and r['extent_m'][1], '.2f')} m",
    'pond': lambda r: f"pond {f(r['pond_speed'], '.2f')} m/s, visit {f(r['visit_s'] and r['visit_s'][1], '.1f')} s, "
                      f"drinks {r['drink_s_game']:.0f} s/game",
    'tree': lambda r: f"tree {r['picked_min']:.2f} picked, {r['home_min']:.2f} home /min",
    'displace': lambda r: f"displace old spot {r['kept']:.0%} kept, {r['wiped']:.0%} wiped, {r['diff'] * 100:+.0f} "
                          f"[{r['diff_ci'][0] * 100:+.0f}, {r['diff_ci'][1] * 100:+.0f}] ({r['trips']} trips)",
    'night': lambda r: f"night alive {r['alive']:.0%}, still at home {f(r['still_home'], '.0%')}, "
                       f"exits {f(r['exits_night'], '.1f')} a night",
}


def main():
    p = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    p.add_argument('brains', nargs='+', help='.pt, run folder, or NAME=path')
    p.add_argument('--games', type=int, default=64)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--only', default=','.join(SKILLS), help='skills to run, comma separated')
    p.add_argument('--world', action='append', default=[], metavar='SKILL=PATH', help='a different world for one skill')
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--displace-games', type=int, help=f'default {DISPLACE_GAMES} x --games')
    a = p.parse_args()
    torch.set_num_threads(a.threads)
    skills = a.only.split(',')
    worlds = {k: CONFIGS / f'{k}.toml' for k in SKILLS}
    for spec in a.world:
        k, _, path = spec.partition('=')
        worlds[k] = Path(path)
    bad = [k for k in skills if k not in SKILLS]
    if bad:
        raise SystemExit(f'no such skill: {", ".join(bad)} (there are {", ".join(SKILLS)})')
    results = {}
    for arg in a.brains:
        name, path = find_brain(arg)
        r = run_brain(path, worlds, skills, a.games, a.seed, a.displace_games or DISPLACE_GAMES * a.games)
        results[name] = {'checkpoint': str(path), **r}
        print(line(name, r), flush=True)
        if a.out:
            a.out.write_text(json.dumps({'seed': a.seed, 'games': a.games, 'worlds': {k: str(worlds[k]) for k in skills},
                                         'brains': results}, indent=1) + '\n')


if __name__ == '__main__':
    main()
