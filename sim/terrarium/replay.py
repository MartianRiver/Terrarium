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
                  'size': size, 'energy': _r(e), 'signal': -1, 'carrying': int(k)}
                 for i, c, (x, y), h, s, e, k, u in zip(world.creature_id[a], world.colony, world.pos[a], world.heading[a],
                                                        speed, world.energy[a], world.crop[a], world.unborn[a]) if not u]
    born = ~world.unborn[a]
    if cfg.grab.on:
        for c, held in zip(creatures, world.holding[a][born]):
            c['holding'] = int(held)
    if cfg.sprint.on:
        for c, burst in zip(creatures, world.sprinting[a][born]):
            c['sprinting'] = int(burst > 0)
    if cfg.flowers.on:
        # seconds of nectar boost left
        for c, boost in zip(creatures, world.nectar[a][born]):
            c['nectar'] = _r(boost / cfg.tick_hz)
    here = world.food_present[a]
    kinds = np.where(np.arange(len(here)) < world.wild, 'common', 'jelly')[here]
    food = [{'id': int(i), 'kind': str(k), 'x': _r(x), 'y': _r(y)}
            for i, k, (x, y) in zip(world.food_id[a][here], kinds, world.food_pos[a][here])]
    blocks = [{'id': int(i), 'x': _r(x), 'y': _r(y), 'angle': _r(t), 'w': b.w, 'h': b.h}
              for i, b, (x, y), t in zip(world.block_id, cfg.block, world.block_pos[a], world.block_angle[a])]
    stores = [{'colony': c, 'jelly': int(j)} for c, j in enumerate(world.store[a])]
    out = {'tick': world.tick, 'creatures': creatures, 'food': food, 'blocks': blocks, 'stores': stores}
    if cfg.night.on:
        out['light'] = _r(world.light()[a])
    if cfg.flowers.on:
        out['flowers'] = [{'id': int(world.flower_id[a, f]), 'x': _r(world.flower_pos[a, f, 0]), 'y': _r(world.flower_pos[a, f, 1])}
                          for f in np.flatnonzero(world.flowers_open[a])]
    if cfg.hatch.on:
        # how far along each egg is, 0 when laid to 1 as it hatches; the hatchling takes the egg's id
        total = max(1, round(cfg.hatch.seconds * cfg.tick_hz))
        out['eggs'] = [{'id': int(world.egg_id[a, i]), 'colony': int(world.colony[i]), 'x': _r(world.egg_pos[a, i, 0]),
                        'y': _r(world.egg_pos[a, i, 1]), 'progress': _r(1 - world.egg[a, i] / total)}
                       for i in np.flatnonzero(world.egg[a])]
    return out


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
