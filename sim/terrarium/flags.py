# Capture the flag, a nursery game ([flag], points 0 is off). Two colonies, each
# with its flag on its nest. Walking into the other nest picks up their flag;
# bringing it onto your own nest captures it, worth `points` to your colony and
# as much off theirs, and the flag goes home. An opponent touching the carrier
# sends the flag straight home. Picking it up and touching a carrier are each
# worth `pickup` of points, so the first steps pay before the first capture.
import numpy as np

from .config import ConfigError


class Flags:
    def __init__(self, world):
        if len(world.nests) != 2:
            raise ConfigError('flag needs exactly two colonies')
        self.world = world
        arenas = world.alive.shape[0]
        # who carries each colony's flag (-1: it's on its nest)
        self.carrier = np.full((arenas, 2), -1)
        self.captures = np.zeros((arenas, 2), int)
        self.pickups = np.zeros((arenas, 2), int)
        self.saves = np.zeros((arenas, 2), int)
        self.gain = np.zeros(world.alive.shape)

    def reset(self, idx: np.ndarray):
        self.carrier[idx] = -1
        self.captures[idx] = 0
        self.pickups[idx] = 0
        self.saves[idx] = 0
        self.gain[idx] = 0

    def carrying(self) -> np.ndarray:
        """Which creatures carry the other colony's flag, (arenas, creatures)."""
        out = np.zeros(self.world.alive.shape, bool)
        for t in range(2):
            a = np.flatnonzero(self.carrier[:, t] >= 0)
            out[a, self.carrier[a, t]] = True
        return out

    def where(self) -> np.ndarray:
        """Each colony's flag, (arenas, 2, 2): on its nest, or with its carrier."""
        w = self.world
        out = np.broadcast_to(w.nests, (len(self.carrier), 2, 2)).copy()
        for t in range(2):
            a = np.flatnonzero(self.carrier[:, t] >= 0)
            out[a, t] = w.pos[a, self.carrier[a, t]]
        return out

    def step(self):
        w, cfg = self.world, self.world.cfg
        p = cfg.flag.points
        touch = 2 * cfg.creature.radius + 0.1
        for t in range(2):
            mine, theirs = w.colony == 1 - t, w.colony == t   # flag t is taken by colony 1 - t
            for a in range(len(self.carrier)):
                c = self.carrier[a, t]
                if c >= 0 and not w.alive[a, c]:
                    self.carrier[a, t] = -1
                elif c < 0:
                    near = np.hypot(*(w.pos[a] - w.nests[t]).T) < cfg.colonies.nest_radius
                    taker = np.flatnonzero(near & mine & w.alive[a])
                    if len(taker):
                        self.carrier[a, t] = taker[0]
                        self.pickups[a, 1 - t] += 1
                        self._pay(a, 1 - t, p * cfg.flag.pickup)
                else:
                    if np.hypot(*(w.pos[a, c] - w.nests[1 - t])) < cfg.colonies.nest_radius:
                        self.carrier[a, t] = -1
                        self.captures[a, 1 - t] += 1
                        self._pay(a, 1 - t, p)
                        continue
                    caught = theirs & w.alive[a] & (np.hypot(*(w.pos[a] - w.pos[a, c]).T) < touch)
                    if caught.any():
                        self.carrier[a, t] = -1
                        self.saves[a, t] += 1
                        self._pay(a, t, p * cfg.flag.pickup)

    def points(self, alive: np.ndarray) -> np.ndarray:
        """What each creature's colony won or lost since last asked, (arenas, creatures)."""
        out, self.gain = self.gain * alive, np.zeros(self.gain.shape)
        return out

    def _pay(self, a: int, team: int, amount: float):
        w = self.world
        self.gain[a] += np.where(w.colony == team, amount, -amount)
