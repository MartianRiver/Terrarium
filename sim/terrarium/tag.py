# Tag, a nursery game ([tag], reach 0 is off). One Terrikin in each arena is it, and
# touching another (bodies within `reach` of each other) passes it on. The new one
# can't tag anyone for `cooldown` seconds, and the one who tagged it for `back` seconds
# (never, if negative): with only the cooldown, two babies stood together and passed it
# back and forth all game, so the one who tags gets a longer head start to run.
# Being it costs `points` a second, shared out among the rest as a gain, so the
# game sums to nothing and one brain learns both chasing and getting away.
import numpy as np


class Tag:
    def __init__(self, world):
        self.world = world
        arenas, n = world.alive.shape
        self.it = np.zeros(arenas, int)
        self.wait = np.zeros(arenas, int)
        self.back = np.full(arenas, -1)     # who passed it on, out of reach of a tag-back
        self.since = np.zeros(arenas, int)  # ticks since the last tag
        # tags made and ticks spent it, by each creature since its arena started
        self.tags = np.zeros((arenas, n), int)
        self.held = np.zeros((arenas, n), int)

    def reset(self, idx: np.ndarray):
        w = self.world
        for a in idx:
            self.it[a] = w.rng.choice(np.flatnonzero(w.alive[a]))
        self.wait[idx] = self._cooldown()
        self.back[idx] = -1
        self.since[idx] = 0
        self.tags[idx] = 0
        self.held[idx] = 0

    def mask(self) -> np.ndarray:
        """Which creature is it, (arenas, creatures)."""
        out = np.zeros(self.world.alive.shape, bool)
        out[np.arange(len(self.it)), self.it] = True
        return out & self.world.alive

    def step(self):
        w, cfg = self.world, self.world.cfg
        rows = np.arange(len(self.it))
        # one that's gone can't be it: the nearest one left is
        lost = ~w.alive[rows, self.it] & w.alive.any(1)
        for a in np.flatnonzero(lost):
            self.it[a] = self._nearest(int(a), w.alive[a])
        self.held[rows, self.it] += w.alive[rows, self.it]
        ready = self.wait == 0
        self.since += 1
        cover = round(cfg.tag.back * cfg.tick_hz) if cfg.tag.back >= 0 else np.iinfo(int).max
        np.maximum(self.wait - 1, 0, out=self.wait)
        far = 2 * cfg.creature.radius + cfg.tag.reach
        for a in np.flatnonzero(ready):
            others = w.alive[a].copy()
            others[self.it[a]] = False
            if self.back[a] >= 0 and self.since[a] <= cover:
                others[self.back[a]] = False
            gap = np.hypot(*(w.pos[a] - w.pos[a, self.it[a]]).T)
            caught = others & (gap < far)
            if caught.any():
                self.tags[a, self.it[a]] += 1
                self.back[a] = self.it[a]
                self.since[a] = 0
                self.it[a] = np.flatnonzero(caught)[gap[caught].argmin()]
                self.wait[a] = self._cooldown()

    def points(self, alive: np.ndarray) -> np.ndarray:
        """Each creature's points for one tick, (arenas, creatures): it pays, the rest share it."""
        cfg = self.world.cfg
        it = self.mask() & alive
        rest = np.maximum(alive.sum(1, keepdims=True) - 1, 1)
        return cfg.tag.points * cfg.dt * np.where(it, -1.0, alive / rest)

    def _nearest(self, a: int, alive: np.ndarray) -> int:
        w = self.world
        gap = np.where(alive, np.hypot(*(w.pos[a] - w.pos[a, self.it[a]]).T), np.inf)
        return int(gap.argmin())

    def _cooldown(self) -> int:
        return round(self.world.cfg.tag.cooldown * self.world.cfg.tick_hz)
