# Smell ([smell] in the world config): food gives off a smell that spreads over a grid laid on each arena, a
# little to each neighbouring cell every tick, and fades. Blocks stop it, except the ones a creature can drag (a
# door), which let some through, as a loose door would. So it reaches round walls and out of a shut room's doors,
# and tells a creature food is that way before it can see any. A creature senses how strong it is where it stands,
# and which way it gets stronger.

import numpy as np

from .config import Smell

# blocks move slowly, so where they stand is drawn onto the grid this often (ticks)
REDRAW = 20
# the weakest smell sensed, and the strongest that still reads differently: a scale of powers of ten
FAINT, STRONG = 1e-4, 10.0


class Field:
    def __init__(self, cfg: Smell, arenas: int, size: float, blocks, leaky: list[int]):
        self.cfg, self.size = cfg, size
        self.n = int(round(size / cfg.cell))
        self.blocks, self.leaky = blocks, leaky
        self.smell = np.zeros((arenas, self.n, self.n), np.float32)
        # share of the smell each cell lets through: 1 open ground, leak in a door, 0 in any other block; and between
        # each cell and the next one along x and along y, as much as the leakier of the two lets through
        self.passes = np.ones_like(self.smell)
        self.gaps = (np.ones_like(self.smell[:, 1:]), np.ones_like(self.smell[:, :, 1:]))
        self.ticks = 0

    def reset(self, arenas: np.ndarray):
        self.smell[arenas] = 0

    def _draw(self, block_pos: np.ndarray, block_angle: np.ndarray):
        c = (np.arange(self.n) + 0.5) * self.cfg.cell - self.size / 2
        x, y = c[None, :, None], c[None, None, :]
        self.passes[:] = 1
        for k, b in enumerate(self.blocks):
            dx, dy = x - block_pos[:, k, 0, None, None], y - block_pos[:, k, 1, None, None]
            cos, sin = np.cos(block_angle[:, k])[:, None, None], np.sin(block_angle[:, k])[:, None, None]
            # a cell counts as in the block when any of it is
            inside = ((np.abs(dx * cos + dy * sin) < b.w / 2 + self.cfg.cell / 2)
                      & (np.abs(-dx * sin + dy * cos) < b.h / 2 + self.cfg.cell / 2))
            np.minimum(self.passes, np.where(inside, self.cfg.leak if k in self.leaky else 0.0, 1.0), out=self.passes)
        p = self.passes
        self.gaps = (np.minimum(p[:, 1:], p[:, :-1]), np.minimum(p[:, :, 1:], p[:, :, :-1]))

    def step(self, food_pos: np.ndarray, present: np.ndarray, block_pos: np.ndarray, block_angle: np.ndarray):
        if self.blocks and self.ticks % REDRAW == 0:
            self._draw(block_pos, block_angle)
        self.ticks += 1
        s, p = self.smell, self.passes
        # to and from each neighbour along x, then y; nothing past the edge
        flow = np.zeros_like(s)
        move = self.gaps[0] * (s[:, 1:] - s[:, :-1])
        flow[:, :-1] += move
        flow[:, 1:] -= move
        move = self.gaps[1] * (s[:, :, 1:] - s[:, :, :-1])
        flow[:, :, :-1] += move
        flow[:, :, 1:] -= move
        s += self.cfg.spread * flow
        s *= 1 - self.cfg.fade
        cell = np.clip(((food_pos + self.size / 2) / self.cfg.cell).astype(int), 0, self.n - 1)
        a, f = np.nonzero(present)
        np.add.at(s, (a, cell[a, f, 0], cell[a, f, 1]), p[a, cell[a, f, 0], cell[a, f, 1]])

    def sense(self, pos: np.ndarray, heading: np.ndarray) -> tuple[np.ndarray, ...]:
        """How strong the smell is where each creature stands, 0 (faint or none) to 1, and which way off its heading
        it gets stronger, as sin and cos (both 0 where it's even)."""
        g = (pos + self.size / 2) / self.cfg.cell - 0.5
        i = np.clip(np.floor(g).astype(int), 0, self.n - 2)
        fx, fy = np.clip(g[..., 0] - i[..., 0], 0, 1), np.clip(g[..., 1] - i[..., 1], 0, 1)
        a = np.arange(len(pos))[:, None]
        level = np.log10(np.maximum(self.smell, FAINT))
        c00, c10 = level[a, i[..., 0], i[..., 1]], level[a, i[..., 0] + 1, i[..., 1]]
        c01, c11 = level[a, i[..., 0], i[..., 1] + 1], level[a, i[..., 0] + 1, i[..., 1] + 1]
        here = (c00 * (1 - fx) * (1 - fy) + c10 * fx * (1 - fy) + c01 * (1 - fx) * fy + c11 * fx * fy)
        # across the four cells round it: which way the smell rises
        dx = (c10 - c00) * (1 - fy) + (c11 - c01) * fy
        dy = (c01 - c00) * (1 - fx) + (c11 - c10) * fx
        rising = np.hypot(dx, dy) > 1e-6
        bearing = np.arctan2(dy, dx) - heading
        strength = (here - np.log10(FAINT)) / (np.log10(STRONG) - np.log10(FAINT))
        return np.clip(strength, 0, 1), np.sin(bearing) * rising, np.cos(bearing) * rising
