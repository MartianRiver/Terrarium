# One Terrikin's mind through an episode, for the viewer's brain window. The episode a replay was recorded from is
# played again, and each time the Terrikin chooses, what its brain took in and made of it is written down: its
# senses, what each ray hit and how far, where its attention went (its own token's weights over itself and the rays,
# in every layer and head), the summary it acts on, its guess at how well things are going, its actions and the
# odds it gave each yes/no. Episodes repeat exactly on the machine that recorded them; each line carries the
# Terrikin's position so the viewer can tell when one recorded elsewhere has parted from this.
#
#   uv run python -m terrarium.mind OUT --brain X.pt --config configs/colony.toml --seed 0 --creature 3

import argparse
import gzip
import json
import math
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .brain import Brain, brain_id, load as load_brain
from .config import Config, load
from .evals import brain_policy
from .forage import Observation
from .log import Logger
from .schema import YES_NO
from .world import World

log = Logger('mind')

FORMAT = 'terrarium-mind'
VERSION = 1
DIGITS = 3


def think(brain: Brain, me: torch.Tensor, kinds: torch.Tensor, rays: torch.Tensor, notes: torch.Tensor | None = None):
    """The brain's forward pass for a batch, step by step: attention from the self token (layers, batch, heads,
    tokens), the self token's units as it enters and after each layer (layers + 1, batch, width), the summary the
    heads read (batch, width; with memory, after its notes are read back in), mean actions and value. Matches
    Brain.forward with the notes it had going in."""
    x = torch.cat([brain.me(me)[:, None], brain.kind(kinds) + brain.ray(rays)], 1)
    attention, units = [], [x[:, 0]]
    for layer in brain.encoder.layers:
        assert isinstance(layer, nn.TransformerEncoderLayer)
        h = layer.norm1(x)
        out, weights = layer.self_attn(h, h, h, need_weights=True, average_attn_weights=False)
        x = x + out
        x = x + layer._ff_block(layer.norm2(x))
        attention.append(weights[:, :, 0])
        units.append(x[:, 0])
    summary, _ = brain.remember(brain.norm(x[:, 0]), brain.blank(len(me)) if notes is None else notes)
    return torch.stack(attention), torch.stack(units), summary, brain.policy(summary), brain.value(summary).squeeze(-1)


def wiring(brain: Brain, strongest: int = 4) -> dict:
    """The strongest connections into each unit, for drawing the brain wired up: senses into the self token's units,
    each layer's units into the next layer's (through its feed-forward part, the two weight matrices multiplied out;
    attention and the pass-through each unit has to itself aren't counted here), and the last units into each
    action and the value (through the final norm's scale). Each is [to, from, weight]."""
    def top(w: torch.Tensor, k: int) -> list:
        k = min(k, w.shape[1])
        weights, index = w.abs().topk(k, 1)
        return [[int(t), int(f), round(float(w[t, f]), 4)] for t in range(w.shape[0]) for f in index[t]]
    with torch.no_grad():
        layers = []
        for layer in brain.encoder.layers:
            assert isinstance(layer, nn.TransformerEncoderLayer)
            layers.append(top(layer.linear2.weight @ layer.linear1.weight, strongest))
        scale = brain.norm.weight
        return {'senses': top(brain.me.weight, strongest), 'layers': layers,
                'actions': top(brain.policy.weight * scale, 3 * strongest),
                'value': top(brain.value.weight * scale, 3 * strongest)}


def odds(brain: Brain, mean: torch.Tensor) -> list[float | None]:
    """The chance of yes for each yes/no action as drawn in replays, None for steering."""
    coins = brain.coins()
    out = []
    for i, name in enumerate(brain.schema['actions']):
        if name not in YES_NO:
            out.append(None)
        elif coins is not None:
            out.append(float(torch.sigmoid(mean[i])))
        else:
            out.append(0.5 * (1 + math.erf(float(mean[i] / brain.log_std[i].detach().exp()) / math.sqrt(2))))
    return out


def _r(x, digits=DIGITS):
    return np.round(np.asarray(x, float), digits).tolist()


def track(cfg: Config, brain_path: Path | str, path: Path | str, seed: int, creature: int,
          ticks: int | None = None) -> int:
    """Write the creature's mind for the episode seed plays (as record() plays it) and return the lines written.
    Stops when it's gone (dead, or its place taken by a hatchling) or at ticks."""
    world = World(cfg, 1, seed)
    brain, meta = load_brain(brain_path)
    brain.eval()
    lines: list[dict] = []
    state = {'seen': False}

    def watch(obs: Observation, held: np.ndarray, notes: torch.Tensor):
        slot = np.flatnonzero((world.creature_id[0] == creature) & ~world.unborn[0])
        if not slot.size or not world.alive[0, slot[0]]:
            return
        i = int(slot[0])
        state['seen'] = True
        with torch.no_grad():
            me, kinds, rays = (torch.from_numpy(x[i:i + 1]) for x in (obs.me, obs.kinds, obs.rays))
            attention, units, summary, mean, value = think(brain, me, kinds, rays, notes[i:i + 1])
        lines.append({'tick': world.tick, 'x': _r(world.pos[0, i, 0]), 'y': _r(world.pos[0, i, 1]),
                      'self': _r(obs.me[i]), 'kinds': obs.kinds[i].tolist(), 'dist': _r(obs.rays[i, :, 0]),
                      'nestmate': obs.rays[i, :, 3].astype(int).tolist(),
                      'attention': _r(attention[:, 0]), 'units': _r(units[:, 0], 2), 'summary': _r(summary[0], 2), 'value': _r(value[0]),
                      'mean': _r(mean[0]), 'odds': [None if p is None else _r(p) for p in odds(brain, mean[0])],
                      'action': _r(held[0, i])})

    act = brain_policy(brain_path, watch=watch)(world)
    limit = ticks if ticks is not None else world.episode_ticks
    for _ in range(limit):
        world.step(act(world))
        gone = not ((world.creature_id[0] == creature) & ~world.unborn[0] & world.alive[0]).any()
        if world.ended[0] or (state['seen'] and gone):
            break
    head = {'format': FORMAT, 'version': VERSION, 'creature': creature, 'seed': seed,
            'brain': {'id': brain_id(brain_path), 'file': Path(brain_path).name, 'shape': brain.shape,
                      'yes_no': brain.yes_no, 'repeat': meta.get('repeat', 1), 'schema': brain.schema},
            'rays': {'count': cfg.vision.rays, 'fov': cfg.vision.fov, 'range': cfg.vision.range},
            'tickHz': cfg.tick_hz}
    with gzip.GzipFile(path, 'wb', mtime=0) as f:
        for line in (head, *lines):
            f.write(json.dumps(line, separators=(',', ':'), allow_nan=False).encode() + b'\n')
    log.info('mind written', path=str(path), creature=creature, lines=len(lines))
    return len(lines)


def main():
    parser = argparse.ArgumentParser(description="Write one Terrikin's mind through an episode, for the viewer.")
    parser.add_argument('out')
    parser.add_argument('--brain', required=True)
    parser.add_argument('--config', default=None)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--creature', type=int, required=True)
    parser.add_argument('--seconds', type=float, default=None, help='stop here (default: the end of the episode)')
    args = parser.parse_args()
    cfg = load(args.config) if args.config else load()
    track(cfg, args.brain, args.out, args.seed, args.creature,
          None if args.seconds is None else round(args.seconds * cfg.tick_hz))


if __name__ == '__main__':
    main()
