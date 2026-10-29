# Hide-and-seek, a nursery game ([seek], prep 0 is off). Colony 0 hides and
# colony 1 seeks. For the first `prep` seconds the seekers can't move, so the
# hiders get away (and can carry blocks to hide behind). After that, every tick
# that any seeker's rays fall on a hider pays the seekers `points` a second and
# costs the hiders the same; a tick with every hider out of sight goes the other
# way. A team's points are shared alike, so it plays as a team.
import numpy as np

HIDERS, SEEKERS = 0, 1


class Seek:
    def __init__(self, world):
        self.world = world
        self.seeker = world.colony == SEEKERS
        # ticks with a hider seen, and ticks played after prep, per arena since it started
        self.seen = np.zeros(world.alive.shape[0], int)
        self.played = np.zeros(world.alive.shape[0], int)
        self.spotted = np.zeros(world.alive.shape[0], bool)

    def reset(self, idx: np.ndarray):
        self.seen[idx] = 0
        self.played[idx] = 0
        self.spotted[idx] = False

    def waiting(self) -> np.ndarray:
        """Share of the hiding time left in each arena, 1 at the start and 0 once seekers can move, (arenas,)."""
        w = self.world
        prep = round(w.cfg.seek.prep * w.cfg.tick_hz)
        return np.clip(1 - w.age / prep, 0, 1) if prep else np.zeros(w.alive.shape[0])

    def hold(self, actions: np.ndarray) -> np.ndarray:
        """Seekers stand still while the hiders get away."""
        frozen = (self.waiting() > 0)[:, None] & self.seeker
        return actions * ~frozen[..., None]

    def step(self):
        from .vision import CREATURE, look
        w = self.world
        sight = look(w)
        # a ray from a seeker that lands on a creature from the other colony: a hider
        found = (sight.kind == CREATURE) & ~sight.nestmate & (self.seeker & w.alive)[..., None]
        live = (self.waiting() == 0) & w.alive[:, ~self.seeker].any(1)
        self.spotted = found.any((1, 2)) & live
        self.seen += self.spotted
        self.played += live

    def points(self, alive: np.ndarray) -> np.ndarray:
        """Each creature's points for one tick, (arenas, creatures)."""
        cfg = self.world.cfg
        live = (self.waiting() == 0)[:, None] & alive
        side = np.where(self.seeker, 1.0, -1.0)
        return cfg.seek.points * cfg.dt * live * side * np.where(self.spotted, 1.0, -1.0)[:, None]
