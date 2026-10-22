# Candidate 1: hand-written physics over numpy arrays, every arena at once.
# Position-based: move everything, push overlaps apart, then read velocity off
# how far things actually moved. Shapes are (arenas, creatures|blocks, ...).

import numpy as np

from scene import (BLOCK_START, BLOCKS, CREATURE_MASS, CREATURES, DT, GROUND_FRICTION, HALF, RADIUS,
                   friction_torque, initial_state, steer)

ITERS = 3
EPS = 1e-9


def rotate(v, cos, sin):
    return np.stack([cos * v[..., 0] - sin * v[..., 1], sin * v[..., 0] + cos * v[..., 1]], -1)


def cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


class VectorWorld:
    def __init__(self, arenas: int, seed: int = 0):
        self.arenas = arenas
        self.pos, self.heading = initial_state(arenas, seed)
        self.vel = np.zeros_like(self.pos)
        nb = len(BLOCKS)
        self.half = np.array([(w / 2, h / 2) for w, h, _ in BLOCKS])
        self.mass = np.array([m for _, _, m in BLOCKS])
        self.inertia = np.array([m * (w * w + h * h) / 12 for w, h, m in BLOCKS])
        self.spin_friction = np.array([friction_torque(w, h, m) for w, h, m in BLOCKS]) / self.inertia
        self.bpos = np.broadcast_to(np.array(BLOCK_START, float), (arenas, nb, 2)).copy()
        self.bang = np.zeros((arenas, nb))
        self.bvel = np.zeros((arenas, nb, 2))
        self.bspin = np.zeros((arenas, nb))
        self.pairs = [(i, j) for i in range(nb) for j in range(nb) if i != j]
        self.not_self = ~np.eye(CREATURES, dtype=bool)

    def step(self, actions: np.ndarray):
        self.heading, self.vel = steer(self.heading, self.vel, actions)
        prev, bprev, aprev = self.pos.copy(), self.bpos.copy(), self.bang.copy()
        self.slow_blocks()
        self.pos += self.vel * DT
        self.bpos += self.bvel * DT
        self.bang += self.bspin * DT

        for _ in range(ITERS):
            self.separate_creatures()
            self.push_blocks()
            for i, j in self.pairs:
                self.separate_blocks(i, j)
            self.wall_blocks()
            np.clip(self.pos, -HALF + RADIUS, HALF - RADIUS, out=self.pos)

        self.vel = (self.pos - prev) / DT
        self.bvel = (self.bpos - bprev) / DT
        self.bspin = (self.bang - aprev) / DT

    def slow_blocks(self):
        speed = np.sqrt((self.bvel * self.bvel).sum(-1))
        self.bvel *= (np.maximum(speed - GROUND_FRICTION * DT, 0) / np.maximum(speed, EPS))[..., None]
        self.bspin = np.sign(self.bspin) * np.maximum(np.abs(self.bspin) - self.spin_friction * DT, 0)

    def separate_creatures(self):
        d = self.pos[:, :, None] - self.pos[:, None]
        dist = np.sqrt((d * d).sum(-1))
        overlap = np.where(self.not_self, np.maximum(2 * RADIUS - dist, 0), 0)
        n = d / np.maximum(dist, EPS)[..., None]
        self.pos += 0.5 * (overlap[..., None] * n).sum(2)

    def push_blocks(self):
        """Circle vs box for every creature and block; the box slides and turns by how off-centre the push is."""
        cos, sin = np.cos(self.bang)[:, None], np.sin(self.bang)[:, None]
        rel = self.pos[:, :, None] - self.bpos[:, None]
        local = rotate(rel, cos, -sin)
        nearest = np.clip(local, -self.half, self.half)
        diff = local - nearest
        dist = np.sqrt((diff * diff).sum(-1))

        # centre inside the box: push out along the shallower axis
        inside = dist < EPS
        depth = self.half - np.abs(local)
        axis = (depth[..., 1] < depth[..., 0])[..., None]
        out = np.where(axis, [0.0, 1.0], [1.0, 0.0]) * np.sign(local + EPS)
        n_local = np.where(inside[..., None], out, diff / np.maximum(dist, EPS)[..., None])
        pen = np.where(inside, RADIUS + np.min(depth, -1), RADIUS - dist)
        pen = np.maximum(pen, 0)

        n = rotate(n_local, cos, sin)
        r = rotate(nearest, cos, sin)
        rxn = cross(r, n)
        w_block = 1 / self.mass + rxn * rxn / self.inertia
        lam = pen / (1 / CREATURE_MASS + w_block)
        self.pos += (n * (lam / CREATURE_MASS)[..., None]).sum(2)
        self.bpos -= (n * (lam / self.mass)[..., None]).sum(1)
        self.bang -= (rxn * lam / self.inertia).sum(1)

    def corners(self, b=None):
        signs = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]], float)
        half = self.half if b is None else self.half[b]
        ang = self.bang if b is None else self.bang[:, b]
        local = signs * half[..., None, :]
        c = rotate(local, np.cos(ang)[..., None], np.sin(ang)[..., None])
        centre = self.bpos if b is None else self.bpos[:, b]
        return c + centre[..., None, :]

    def separate_blocks(self, i, j):
        """Deepest corner of block i inside block j, pushed out along j's nearest face."""
        corners = self.corners(i)
        cos, sin = np.cos(self.bang[:, j])[:, None], np.sin(self.bang[:, j])[:, None]
        local = rotate(corners - self.bpos[:, j, None], cos, -sin)
        depth = self.half[j] - np.abs(local)
        pen_c = np.where((depth > 0).all(-1), depth.min(-1), 0)
        k = pen_c.argmax(-1)
        rows = np.arange(self.arenas)
        pen = pen_c[rows, k]
        lc, dc = local[rows, k], depth[rows, k]
        axis = (dc[:, 1] < dc[:, 0])[:, None]
        n = rotate(np.where(axis, [0.0, 1.0], [1.0, 0.0]) * np.sign(lc + EPS), cos[:, 0], sin[:, 0])
        point = corners[rows, k]
        ri, rj = point - self.bpos[:, i], point - self.bpos[:, j]
        xi, xj = cross(ri, n), cross(rj, n)
        w = (1 / self.mass[i] + xi * xi / self.inertia[i] + 1 / self.mass[j] + xj * xj / self.inertia[j])
        lam = pen / w
        self.bpos[:, i] += n * (lam / self.mass[i])[:, None]
        self.bang[:, i] += xi * lam / self.inertia[i]
        self.bpos[:, j] -= n * (lam / self.mass[j])[:, None]
        self.bang[:, j] -= xj * lam / self.inertia[j]

    def wall_blocks(self):
        for n in ([1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]):
            n = np.array(n)
            corners = self.corners()
            pen_c = -(corners @ n + HALF)
            k = pen_c.argmax(-1)
            pen = np.maximum(np.take_along_axis(pen_c, k[..., None], -1)[..., 0], 0)
            point = np.take_along_axis(corners, k[..., None, None], -2)[..., 0, :]
            r = point - self.bpos
            rxn = cross(r, n)
            lam = pen / (1 / self.mass + rxn * rxn / self.inertia)
            self.bpos += n * (lam / self.mass)[..., None]
            self.bang += rxn * lam / self.inertia

    def state(self):
        return self.pos, self.heading, self.bpos, self.bang
