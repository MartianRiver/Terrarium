# Replays: what the viewer plays back. A gzipped JSON-lines file, a header line
# then one Frame per tick, in the shapes viewer/src/world.ts defines. The format
# only ever gains fields; anything else bumps VERSION, and the viewer keeps
# reading the old one (docs/releasing.md).

import gzip
import json
from pathlib import Path

import numpy as np

from .world import World

FORMAT = 'terrarium-replay'
VERSION = 1
# the viewer's blob is modelled at this radius, so a creature's size is its radius over this
BLOB_RADIUS = 0.45
# millimetres and milliradians: plenty for drawing, and a third of the file
DIGITS = 3


def _r(v) -> float:
    return round(float(v), DIGITS)


def header(world: World, arena: int, source: dict) -> dict:
    cfg = world.cfg
    nests = [{'colony': c, 'x': _r(x), 'y': _r(y), 'radius': cfg.colonies.nest_radius}
             for c, (x, y) in enumerate(world.nests)]
    info = {'width': cfg.arena.size, 'height': cfg.arena.size, 'tickHz': cfg.tick_hz,
            'maxSpeed': cfg.creature.max_speed, 'nests': nests}
    return {'format': FORMAT, 'version': VERSION, 'info': info,
            'source': {**source, 'arena': arena, 'config': cfg.to_dict()}}


def frame(world: World, a: int) -> dict:
    cfg = world.cfg
    size = _r(cfg.creature.radius / BLOB_RADIUS)
    speed = np.hypot(world.vel[a, :, 0], world.vel[a, :, 1])
    creatures = [{'id': int(i), 'colony': int(c), 'x': _r(x), 'y': _r(y), 'heading': _r(h), 'speed': _r(s),
                  'size': size, 'energy': _r(e), 'signal': -1}
                 for i, c, (x, y), h, s, e in zip(world.creature_id, world.colony, world.pos[a], world.heading[a],
                                                  speed, world.energy[a])]
    here = world.food_present[a]
    food = [{'id': int(i), 'kind': 'common', 'x': _r(x), 'y': _r(y)}
            for i, (x, y) in zip(world.food_id[a][here], world.food_pos[a][here])]
    blocks = [{'id': int(i), 'x': _r(x), 'y': _r(y), 'angle': _r(t), 'w': b.w, 'h': b.h}
              for i, b, (x, y), t in zip(world.block_id, cfg.block, world.block_pos[a], world.block_angle[a])]
    return {'tick': world.tick, 'creatures': creatures, 'food': food, 'blocks': blocks}


class Writer:
    def __init__(self, path: Path | str, head: dict):
        self.raw = open(path, 'wb')
        # no name or time in the gzip header, so the same run writes the same bytes
        self.file = gzip.GzipFile(fileobj=self.raw, mode='wb', filename='', mtime=0)
        self.frames = 0
        self._line(head)

    def _line(self, obj):
        self.file.write(json.dumps(obj, separators=(',', ':'), allow_nan=False).encode() + b'\n')

    def write(self, frame: dict):
        self._line(frame)
        self.frames += 1

    def close(self):
        self.file.close()
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read(path: Path | str) -> tuple[dict, list[dict]]:
    with gzip.open(path, 'rt') as f:
        lines = f.read().splitlines()
    head = json.loads(lines[0])
    if head.get('format') != FORMAT:
        raise ValueError(f'{path}: not a replay')
    return head, [json.loads(line) for line in lines[1:]]
