# Peekaboo, a nursery game for memory ([peek], show 0 is off). A berry turns up
# in front of a Terrikin, in sight for `show` seconds, then goes out of sight but
# stays where it is. Finding it pays `points` to everyone (the first to touch it
# eats it), and the next one turns up `gap` seconds later. One nobody finds in
# `timeout` seconds after it hid goes somewhere else. With `spin`, everyone is
# turned round at random the moment it hides, so walking straight on isn't enough:
# a brain has to remember where it was, from its home bearing or its own turns.
import numpy as np

from .config import ConfigError

TRIES = 50


class Peek:
    def __init__(self, world):
        if world.wild != 1:
            raise ConfigError('peek needs exactly one food, the berry')
        self.world = world
        arenas = world.alive.shape[0]
        self.since = np.zeros(arenas, int)      # ticks since the berry turned up
        self.last = np.full(arenas, -1)         # its food id, to see a new one
        self.found = np.zeros(arenas, int)
        self.missed = np.zeros(arenas, int)
        self.waited = np.zeros(arenas, int)     # ticks from hiding to being found, summed over finds
        self.gain = np.zeros(arenas)

    def reset(self, idx: np.ndarray):
        self.since[idx] = 0
        self.last[idx] = -1
        self.found[idx] = 0
        self.missed[idx] = 0
        self.waited[idx] = 0
        self.gain[idx] = 0

    @property
    def hidden(self) -> np.ndarray:
        """Whether the berry is out of sight, (arenas,)."""
        return self.world.food_present[:, 0] & (self.since >= self._ticks(self.world.cfg.peek.show))

    def step(self):
        w, p = self.world, self.world.cfg.peek
        show = self._ticks(p.show)
        for a in np.flatnonzero(w.food_present[:, 0] & (w.food_id[:, 0] != self.last)):
            self.last[a] = w.food_id[a, 0]
            self.since[a] = 0
            self._place(a)
        here = w.food_present[:, 0]
        self.since[here] += 1
        if p.spin:
            for a in np.flatnonzero(here & (self.since == show)):
                w.heading[a] = w.rng.uniform(-np.pi, np.pi, w.heading.shape[1])
        reach = w.cfg.creature.radius + w.cfg.food.radius
        gap = np.hypot(*(w.pos - w.food_pos[:, None, 0]).transpose(2, 0, 1))
        touched = here & ((gap < reach) & w.alive).any(1)
        for a in np.flatnonzero(touched):
            self.found[a] += 1
            self.waited[a] += max(self.since[a] - show, 0)
            self.gain[a] += p.points
            w.food_regrow[a, 0] = self._ticks(p.gap)
        for a in np.flatnonzero(here & ~touched & (self.since >= show + self._ticks(p.timeout))):
            self.missed[a] += 1
            w._grow(a, 0)

    def points(self, alive: np.ndarray) -> np.ndarray:
        """What each creature's arena won since last asked, (arenas, creatures)."""
        out, self.gain = self.gain[:, None] * alive, np.zeros(self.gain.shape)
        return out

    def _place(self, a):
        """In front of a Terrikin on one of its rays (between them, a berry this small can hide), on open ground."""
        w, cfg = self.world, self.world.cfg
        alive = np.flatnonzero(w.alive[a])
        if not len(alive):
            return
        room = cfg.arena.size / 2 - cfg.food.clearance
        half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2) + cfg.food.radius
        i = w.rng.choice(alive)
        # the middle of the fan
        v = cfg.vision
        rays = np.linspace(-v.fov / 2, v.fov / 2, v.rays)
        rays = rays[np.abs(rays) <= 0.3 * v.fov]
        for _ in range(TRIES):
            t = w.heading[a, i] + w.rng.choice(rays)
            r = w.rng.uniform(cfg.peek.near, cfg.peek.far)
            spot = w.pos[a, i] + r * np.array([np.cos(t), np.sin(t)])
            if (np.abs(spot) <= room).all() and not (len(half) and w._on_block(a, spot, half)):
                w.food_pos[a, 0] = spot
                return
        # facing a wall up close: anywhere, never pulled back inside (a brain learned to park at the
        # wall and have every berry land in front of its face)
        w.food_pos[a, 0] = w._open_ground(a)

    def _ticks(self, seconds: float) -> int:
        return round(seconds * self.world.cfg.tick_hz)
