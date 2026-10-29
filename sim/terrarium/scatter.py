# [arena] scatter: every block moves up to `scatter` m from where it's set and turns any way, anew each episode, so a
# game played round them can't be learned as one layout. A draw that would overlap another block, cross a wall or reach
# into a nest's spawn ring is drawn again; an arena where they won't all fit keeps the layout as set.
from dataclasses import replace

import numpy as np

GAP = 0.1
TRIES = 30


def corners(b) -> np.ndarray:
    c, s = np.cos(b.angle), np.sin(b.angle)
    u, v = np.array([c, s]) * b.w / 2, np.array([-s, c]) * b.h / 2
    mid = np.array([b.x, b.y])
    return np.array([mid + u + v, mid + u - v, mid - u - v, mid - u + v])


def apart(p: np.ndarray, q: np.ndarray, gap: float) -> bool:
    """Whether two boxes (corners (4, 2)) are at least gap apart along one of their edges' normals."""
    for box in (p, q):
        for e in (box[1] - box[0], box[3] - box[0]):
            n = np.array([-e[1], e[0]]) / np.hypot(*e)
            a, b = p @ n, q @ n
            if a.max() + gap <= b.min() or b.max() + gap <= a.min():
                return True
    return False


def scatter(world, idx: np.ndarray):
    from .world import box_gap
    cfg = world.cfg
    room = cfg.arena.size / 2 - GAP
    reach = cfg.colonies.spawn_ring + cfg.creature.radius + GAP
    every = list(range(len(cfg.block)))
    for a in idx:
        for _ in range(TRIES):
            placed = []
            for b in cfg.block:
                for _ in range(TRIES):
                    d, t = cfg.arena.scatter * np.sqrt(world.rng.uniform()), world.rng.uniform(0, 2 * np.pi)
                    moved = replace(b, x=b.x + d * np.cos(t), y=b.y + d * np.sin(t), angle=world.rng.uniform(0, np.pi))
                    box = corners(moved)
                    if ((np.abs(box) <= room).all() and (box_gap(world.nests, moved) > reach).all()
                            and all(apart(box, corners(p), GAP) for p in placed)):
                        placed.append(moved)
                        break
                else:
                    break
            if len(placed) == len(cfg.block):
                world.physics.shift([a], every, np.array([(p.x, p.y) for p in placed]), np.array([p.angle for p in placed]))
                break
