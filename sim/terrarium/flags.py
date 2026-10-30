# Capture the flag, a nursery game ([flag], points 0 is off). Two colonies, each
# with its flag on its nest. Walking into the other nest picks up their flag;
# bringing it onto your own nest captures it, worth `points` to your colony and
# as much off theirs, and the flag goes home.
#
# With `steal`, a touch from the other side takes the flag off its carrier, and
# nobody can take it off the new one for `guard` seconds. A colony that gets its
# own flag back has to carry it home. A carrier can put the flag down (unload) for
# a teammate to pick up, the one who put it down only after `guard` seconds; a flag
# left lying goes home after `lie`, and so does a carrier's that falls.
# Without it, an opponent touching the carrier sends the flag straight home.
#
# Picking a flag up from a nest and taking one off a carrier are each worth
# `pickup` of points, so the first steps pay before the first capture.
import numpy as np

from .config import ConfigError


class Flags:
    def __init__(self, world):
        if len(world.nests) != 2:
            raise ConfigError('flag needs exactly two colonies')
        self.world = world
        arenas = world.alive.shape[0]
        # who carries each colony's flag (-1: nobody), and where it lies when it's down
        self.carrier = np.full((arenas, 2), -1)
        self.down = np.zeros((arenas, 2), bool)
        self.spot = np.zeros((arenas, 2, 2))
        self.lie = np.zeros((arenas, 2), int)
        # ticks before a carrier can be robbed (or the one who put a flag down can pick it up again)
        self.guard = np.zeros((arenas, 2), int)
        self.dropper = np.full((arenas, 2), -1)
        self.captures = np.zeros((arenas, 2), int)
        self.pickups = np.zeros((arenas, 2), int)
        self.saves = np.zeros((arenas, 2), int)
        self.gain = np.zeros(world.alive.shape)

    def reset(self, idx: np.ndarray):
        self.carrier[idx] = -1
        self.down[idx] = False
        self.guard[idx] = 0
        self.dropper[idx] = -1
        self.captures[idx] = 0
        self.pickups[idx] = 0
        self.saves[idx] = 0
        self.gain[idx] = 0

    def held(self) -> np.ndarray:
        """Whose flag each creature carries, -1 for none, (arenas, creatures)."""
        out = np.full(self.world.alive.shape, -1)
        for t in range(2):
            a = np.flatnonzero(self.carrier[:, t] >= 0)
            out[a, self.carrier[a, t]] = t
        return out

    def carrying(self) -> np.ndarray:
        """Which creatures carry a flag, either one, (arenas, creatures)."""
        return self.held() >= 0

    def where(self) -> np.ndarray:
        """Each colony's flag, (arenas, 2, 2): on its nest, lying where it was put down, or with its carrier."""
        w = self.world
        out = np.broadcast_to(w.nests, (len(self.carrier), 2, 2)).copy()
        out[self.down] = self.spot[self.down]
        for t in range(2):
            a = np.flatnonzero(self.carrier[:, t] >= 0)
            out[a, t] = w.pos[a, self.carrier[a, t]]
        return out

    def step(self, drop: np.ndarray):
        """drop (arenas, creatures): carriers putting their flag down (with steal)."""
        w, f = self.world, self.world.cfg.flag
        np.maximum(self.guard - 1, 0, out=self.guard)
        for t in range(2):
            for a in range(len(self.carrier)):
                c = self.carrier[a, t]
                if c >= 0 and not w.alive[a, c]:
                    if f.steal:
                        self._put_down(a, t, -1)
                    else:
                        self.carrier[a, t] = -1
                elif self.down[a, t]:
                    self._lying(a, t)
                elif c < 0:
                    self._from_nest(a, t)
                else:
                    self._carried(a, t, c, drop[a, c])

    def points(self, alive: np.ndarray) -> np.ndarray:
        """What each creature's colony won or lost since last asked, (arenas, creatures)."""
        out, self.gain = self.gain * alive, np.zeros(self.gain.shape)
        return out

    def _from_nest(self, a: int, t: int):
        w, cfg = self.world, self.world.cfg
        near = np.hypot(*(w.pos[a] - w.nests[t]).T) < cfg.colonies.nest_radius
        taker = np.flatnonzero(near & (w.colony == 1 - t) & w.alive[a])
        if len(taker):
            self.carrier[a, t] = taker[0]
            self.guard[a, t] = self._ticks(cfg.flag.guard)
            self.pickups[a, 1 - t] += 1
            self._pay(a, 1 - t, cfg.flag.points * cfg.flag.pickup)

    def _carried(self, a: int, t: int, c: int, drop: bool):
        w, cfg = self.world, self.world.cfg
        f, side = cfg.flag, w.colony[c]
        at_nest = np.hypot(*(w.pos[a, c] - w.nests[side])) < cfg.colonies.nest_radius
        if at_nest and side != t:
            self.carrier[a, t] = -1
            self.captures[a, side] += 1
            self._pay(a, side, f.points)
            return
        if at_nest:
            # got back home
            self.carrier[a, t] = -1
            return
        if f.steal and drop:
            self._put_down(a, t, c)
            return
        gap = np.hypot(*(w.pos[a] - w.pos[a, c]).T)
        robbers = (w.colony != side) & w.alive[a] & (gap < 2 * cfg.creature.radius + 0.1)
        if not robbers.any() or self.guard[a, t]:
            return
        if f.steal:
            r = np.flatnonzero(robbers)[gap[robbers].argmin()]
            self.carrier[a, t] = r
            self.guard[a, t] = self._ticks(f.guard)
        else:
            self.carrier[a, t] = -1
        robber = 1 - side
        if robber == t:
            self.saves[a, t] += 1
        self._pay(a, robber, f.points * f.pickup)

    def _put_down(self, a: int, t: int, by: int):
        w = self.world
        self.spot[a, t] = w.pos[a, self.carrier[a, t]]
        self.carrier[a, t] = -1
        self.down[a, t] = True
        self.lie[a, t] = self._ticks(w.cfg.flag.lie)
        self.dropper[a, t] = by
        self.guard[a, t] = self._ticks(w.cfg.flag.guard) if by >= 0 else 0

    def _lying(self, a: int, t: int):
        w = self.world
        self.lie[a, t] -= 1
        if self.lie[a, t] <= 0:
            self.down[a, t] = False
            return
        gap = np.hypot(*(w.pos[a] - self.spot[a, t]).T)
        near = w.alive[a] & (gap < w.cfg.creature.radius + 0.1)
        if self.guard[a, t] and self.dropper[a, t] >= 0:
            near[self.dropper[a, t]] = False
        if near.any():
            self.carrier[a, t] = np.flatnonzero(near)[gap[near].argmin()]
            self.down[a, t] = False
            self.guard[a, t] = self._ticks(w.cfg.flag.guard)

    def _ticks(self, seconds: float) -> int:
        return round(seconds * self.world.cfg.tick_hz)

    def _pay(self, a: int, team: int, amount: float):
        w = self.world
        self.gain[a] += np.where(w.colony == team, amount, -amount)
