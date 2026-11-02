# The apple tree, a nursery game for jumping ([tree], points 0 is off). One
# block is a tree's trunk, and every apple grows hanging from its branches
# somewhere round it, `reach` metres above what a Terrikin standing under it can
# get to: it has to go and stand under one and jump ([jump]). Each apple taken
# pays `points` to everyone in the arena, hungry or not, and another grows on the
# tree as food grows back. Rays see a hanging apple where it hangs, as food. Each
# jump costs its jumper `hop` points: without it, the first brain hopped round the
# tree non-stop (in the air 87% of the time), taking every apple it passed under.
import numpy as np

from .config import ConfigError

TRIES = 50


class Tree:
    def __init__(self, world):
        t = world.cfg.tree
        if not 0 <= t.trunk < len(world.cfg.block):
            raise ConfigError('[tree] trunk must be one of the blocks')
        if t.reach > 0 and t.reach >= world.cfg.jump.height:
            raise ConfigError('[tree] reach must be below [jump] height, or no apple can be taken')
        self.world = world
        self.seen = np.zeros(world.alive.shape[0])
        self.hops = np.zeros(world.alive.shape)

    def reset(self, idx: np.ndarray):
        self.seen[idx] = 0
        self.hops[idx] = 0

    def reaching(self) -> np.ndarray:
        """Who is high enough to take an apple, (arenas, creatures)."""
        w = self.world
        return w.alive & (w.z >= w.cfg.tree.reach)

    def spot(self, a: int) -> np.ndarray:
        """Where a new apple hangs: round the trunk, over open ground inside the walls."""
        w, cfg = self.world, self.world.cfg
        t = cfg.tree
        middle = w.physics.block_pos[a, t.trunk]
        room = cfg.arena.size / 2 - cfg.food.radius
        # it may hang over its own trunk's corner, not over any other block
        half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2) + cfg.food.radius
        half[t.trunk] = 0
        for _ in range(TRIES):
            angle = w.rng.uniform(-np.pi, np.pi)
            spot = middle + w.rng.uniform(t.near, t.far) * np.array([np.cos(angle), np.sin(angle)])
            if (np.abs(spot) <= room).all() and not w._on_block(a, spot, half):
                return spot
        return middle + t.far * np.array([1.0, 0.0])

    def points(self, alive: np.ndarray) -> np.ndarray:
        """What each creature's arena won since last asked, (arenas, creatures)."""
        w, t = self.world, self.world.cfg.tree
        now = w.meals.sum(1).astype(float)
        out = (now - self.seen)[:, None] * t.points * alive - (w.jumps - self.hops) * t.hop
        self.seen, self.hops = now, w.jumps.astype(float)
        return out
