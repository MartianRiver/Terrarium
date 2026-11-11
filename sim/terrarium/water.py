# [water]: thirst as a second need beside energy. Each nim has water (1 full) that falls over time and rises while its
# centre is in a pond; at 0 it dies where starving would. Ponds are flat ground, so nothing stops at their edge:
# rays say how far off it is (vision's `pond`, as `own_nest` does for a nest), and food, flowers and moved blocks
# keep out of them. Going to water is learned; only this is the world's. With several colonies a pond goes where no nest
# is more than FAIR m nearer it than another, at `distance` from the middle of the nests.
import numpy as np

from .log import Logger
from .vision import hit_circles

TRIES = 100
# how much nearer one colony's nest may be to a pond than another's, m
FAIR = 1.0
log = Logger('water')


class Ponds:
    def __init__(self, world):
        self.world = world
        # (arenas, ponds, 2): drawn anew each game, from the arena's own stream
        self.pos = np.zeros((world.arenas, world.cfg.water.ponds, 2))
        # games where no spot was `distance` from the nest and the ponds went wherever they fitted
        self.fell_back = np.zeros(world.arenas, int)

    def reset(self, idx: np.ndarray):
        self.fell_back[idx] = 0
        for a in idx:
            self._place(a)

    def _place(self, a):
        """Each pond `distance` from the middle of the nests (colony 0's, with one colony) at a random angle, where no
        colony is much nearer than another; failing that, anywhere it fits."""
        w, cfg = self.world, self.world.cfg
        t = cfg.water
        rng = w.rngs[a]
        room = cfg.arena.size / 2 - t.radius
        half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2) + t.radius
        nest_gap = cfg.colonies.nest_radius + t.radius
        middle = w.nests.mean(0)
        for k in range(t.ponds):
            def clear(p):
                return ((np.abs(p) <= room).all()
                        and (np.hypot(*(w.nests - p).T) >= nest_gap).all()
                        and not (len(half) and w._on_block(a, p, half))
                        and (np.hypot(*(self.pos[a, :k] - p).T) >= 2 * t.radius).all())

            def fair(p):
                gap = np.hypot(*(w.nests - p).T)
                return gap.max() - gap.min() <= FAIR

            def at_distance():
                angle = rng.uniform(0, 2 * np.pi)
                return middle + t.distance * np.array([np.cos(angle), np.sin(angle)])

            def anywhere():
                return rng.uniform(-room, room, 2)

            p = next((p for p in (at_distance() for _ in range(TRIES)) if clear(p) and fair(p)), None)
            if p is None:
                self.fell_back[a] = 1
                log.warn('pond not placed at its distance from the nests', arena=int(a), pond=k)
                p = next((p for p in (anywhere() for _ in range(TRIES)) if clear(p) and fair(p)), None)
            if p is None:
                log.warn('no room for a pond, placing it anyway', arena=int(a), pond=k)
                p = anywhere()
            self.pos[a, k] = p

    def covers(self, a, p: np.ndarray, margin: float = 0.0) -> bool:
        """Whether a point (or a thing this wide) in arena a touches a pond."""
        d = self.pos[a] - p
        return bool((np.hypot(d[:, 0], d[:, 1]) < self.world.cfg.water.radius + margin).any())

    def inside(self) -> np.ndarray:
        """(arenas, creatures): whose centre is in a pond."""
        d = self.world.pos[:, :, None] - self.pos[:, None]                    # A,N,P,2
        return ((d[..., 0] ** 2 + d[..., 1] ** 2) < self.world.cfg.water.radius ** 2).any(-1)

    def step(self, share: np.ndarray | float):
        """One tick of thirst and drinking for the living; share is what the young pay of each cost."""
        w = self.world
        t, dt = w.cfg.water, w.cfg.dt
        # not clipped at 0 yet: a drink has to cover what the drain took past empty, or it dies
        dried = w.water - t.drain * dt * share
        floor = np.clip(dried, 0, 1)
        # lapping takes standing still: the rate falls with speed, to nothing at `still` m/s
        slow = np.clip(1 - np.hypot(w.vel[..., 0], w.vel[..., 1]) / t.still, 0, 1) if t.still > 0 else 1.0
        sip = np.clip(floor + t.drink * dt * self.inside() * slow, 0, 1) - floor
        w.drank += np.where(w.alive, sip, 0)
        w.water = np.where(w.alive, np.clip(dried + sip, 0, 1), w.water)

    def edge(self, origin, dirs, start) -> np.ndarray:
        """(arenas, creatures, rays): how far along each ray a pond's edge is, inf for none; ponds don't stop a ray."""
        centres = self.pos
        every = np.ones((origin.shape[0], origin.shape[1], len(centres[0])), bool)
        return hit_circles(origin, dirs, centres, self.world.cfg.water.radius, every, start).min(-1, initial=np.inf)
