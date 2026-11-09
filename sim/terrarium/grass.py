# [grass]: food as a field on the ground instead of objects. Each arena has a grid of cover (0 bare to 1 full), full in
# a few meadows and `base` elsewhere; a nim whose energy is below 1 eats the cell it stands on by itself, and cover
# grows back toward what the cell started with. With `still` set grazing takes standing still, so walking over a
# meadow feeds nothing. Rays don't see it: the brain feels the cover under it and which way it rises (as smell does).
import numpy as np

from .log import Logger

TRIES = 100
# how far round it a nim feels the cover rise, m
FEEL = 1.5
log = Logger('grass')


class Meadows:
    def __init__(self, world):
        self.world = world
        g = world.cfg.grass
        self.size = world.cfg.arena.size
        self.n = int(np.ceil(self.size / g.cell - 1e-9))
        # (arenas, meadows, 2): drawn anew each game, from the arena's own stream
        self.pos = np.zeros((world.arenas, g.meadows, 2))
        # games where no spot was `distance` from the nest and a meadow went wherever it fitted
        self.fell_back = np.zeros(world.arenas, int)
        # what each cell grows back to, and what's left of it
        self.start = np.zeros((world.arenas, self.n, self.n), np.float32)
        self.cover = np.zeros_like(self.start)
        mid = (np.arange(self.n) + 0.5) * g.cell - self.size / 2
        self.mid = mid
        self.cells = np.stack(np.meshgrid(mid, mid, indexing='ij'), -1)             # n,n,2
        reach = int(FEEL / g.cell)
        near = [(i, j) for i in range(-reach, reach + 1) for j in range(-reach, reach + 1)
                if np.hypot(i, j) * g.cell <= FEEL]
        self.window = np.array(near)

    def reset(self, idx: np.ndarray):
        self.fell_back[idx] = 0
        for a in idx:
            self._place(a)
            self.fill(a)

    def fill(self, a):
        """Arena a's cover from where its meadows are: full inside one, `base` outside, and every cell grows back to that."""
        g = self.world.cfg.grass
        inside = np.zeros((self.n, self.n), bool)
        for p in self.pos[a]:
            inside |= np.hypot(*(self.cells - p).transpose(2, 0, 1)) < g.radius
        self.start[a] = np.where(inside, 1.0, g.base)
        self.cover[a] = self.start[a]

    def _place(self, a):
        """Each meadow `distance` from colony 0's nest at a random angle; failing that, anywhere it fits."""
        w, cfg = self.world, self.world.cfg
        t = cfg.grass
        rng = w.rngs[a]
        room = cfg.arena.size / 2 - t.radius
        half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2) + t.radius
        nest_gap = cfg.colonies.nest_radius + t.radius
        for k in range(t.meadows):
            def clear(p):
                return ((np.abs(p) <= room).all()
                        and (np.hypot(*(w.nests - p).T) >= nest_gap).all()
                        and not (len(half) and w._on_block(a, p, half))
                        and not (w.ponds and w.ponds.covers(a, p, t.radius))
                        and (np.hypot(*(self.pos[a, :k] - p).T) >= 2 * t.radius).all())

            def at_distance():
                angle = rng.uniform(0, 2 * np.pi)
                return w.nests[0] + t.distance * np.array([np.cos(angle), np.sin(angle)])

            def anywhere():
                return rng.uniform(-room, room, 2)

            p = next((p for p in (at_distance() for _ in range(TRIES)) if clear(p)), None)
            if p is None:
                self.fell_back[a] = 1
                log.warn('meadow not placed at its distance from the nest', arena=int(a), meadow=k)
                p = next((p for p in (anywhere() for _ in range(TRIES)) if clear(p)), None)
            if p is None:
                log.warn('no room for a meadow, placing it anyway', arena=int(a), meadow=k)
                p = anywhere()
            self.pos[a, k] = p

    def cell_of(self, pos: np.ndarray) -> np.ndarray:
        """(arenas, creatures, 2): the grid cell each position is in."""
        return np.clip(np.floor((pos + self.size / 2) / self.world.cfg.grass.cell).astype(int), 0, self.n - 1)

    def under(self) -> np.ndarray:
        """(arenas, creatures): the cover each nim stands on."""
        c = self.cell_of(self.world.pos)
        return self.cover[np.arange(self.world.arenas)[:, None], c[..., 0], c[..., 1]]

    def step(self, share: np.ndarray | float):
        """One tick of regrowth and grazing; share is what the young pay of what a grown nim would for the same meal."""
        w = self.world
        g, dt = w.cfg.grass, w.cfg.dt
        np.minimum(self.cover + np.float32(g.regrow * dt), self.start, out=self.cover)
        if g.bite <= 0 or g.food <= 0:
            return
        # lapping the cover takes standing still: the rate falls with speed, to nothing at `still` m/s
        slow = np.clip(1 - np.hypot(w.vel[..., 0], w.vel[..., 1]) / g.still, 0, 1) if g.still > 0 else 1.0
        gain = np.minimum(g.bite * dt * g.food * slow, 1 - w.energy) * w.alive
        want = gain / g.food * share
        c = self.cell_of(w.pos)
        flat = (np.arange(w.arenas)[:, None] * self.n + c[..., 0]) * self.n + c[..., 1]
        cells = w.arenas * self.n * self.n
        # nims sharing a cell share what's left of it
        asked = np.bincount(flat.ravel(), want.ravel(), cells)
        left = self.cover.reshape(-1).astype(np.float64)
        fair = np.where(asked > left, left / np.maximum(asked, 1e-300), 1.0)[flat]
        gain, want = gain * fair, want * fair
        self.cover -= np.bincount(flat.ravel(), want.ravel(), cells).reshape(self.cover.shape).astype(np.float32)
        np.maximum(self.cover, 0, out=self.cover)
        w.energy += gain
        np.clip(w.energy, 0, 1, out=w.energy)
        w.fed += gain
        w.nourished += gain
        w.grazed += gain
        w.grazing += dt * (gain > 0)

    def sense(self, heading: np.ndarray) -> tuple[np.ndarray, ...]:
        """The cover under each nim, and which way off its heading it rises within FEEL m, as sin and cos (both 0
        where it's even all round)."""
        w = self.world
        c = self.cell_of(w.pos)
        at = np.clip(c[:, :, None] + self.window, 0, self.n - 1)                    # A,N,K,2
        a = np.arange(w.arenas)[:, None, None]
        seen = self.cover[a, at[..., 0], at[..., 1]].astype(np.float64)             # A,N,K
        off = self.mid[at] - w.pos[:, :, None]                                      # A,N,K,2
        slope = ((seen - seen.mean(-1, keepdims=True))[..., None] * off).sum(2)
        rising = np.hypot(slope[..., 0], slope[..., 1]) > 1e-6
        bearing = np.arctan2(slope[..., 1], slope[..., 0]) - heading
        return self.under(), np.sin(bearing) * rising, np.cos(bearing) * rising

    def bytes(self, a: int) -> np.ndarray:
        """Arena a's cover as bytes, 255 full: n × n, index ix * n + iy for the cell ix across and iy up."""
        return np.rint(self.cover[a] * 255).astype(np.uint8)
