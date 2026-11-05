# The apple tree, a nursery game for jumping ([tree], points 0 is off). One
# block is a tree's trunk, and every apple grows hanging from its branches
# somewhere round it, `reach` metres above what a Terrikin standing under it can
# get to: it has to go and stand under one and jump ([jump]). Each apple taken
# pays `points` to everyone in the arena, hungry or not, and another grows on the
# tree as food grows back. Rays see a hanging apple where it hangs, as food. Each
# jump costs its jumper `hop` points: without it, the first brain hopped round the
# tree non-stop (in the air 87% of the time), taking every apple it passed under.
# With `home`, an apple taken goes in the crop, so one with a full crop can't take
# another, and it pays only once it's unloaded in the nest: carried home. With `move`, the tree goes somewhere new
# every so often in a game (where [arena] scatter would draw it), its apples growing round it there, so where it
# stands has to be found again and remembered afresh. With `start`, each episode starts with the Terrikins ringed
# round the trunk, facing it, so the first find is free and only the trips after it need remembering. With
# `burrow`, unloading at home takes the carrier into the nest and back up at its middle turned any way, so the way
# back out can't be read off where it came in.
import numpy as np

from . import scatter
from .config import ConfigError

TRIES = 50


class Tree:
    def __init__(self, world):
        t = world.cfg.tree
        if not 0 <= t.trunk < len(world.cfg.block):
            raise ConfigError('[tree] trunk must be one of the blocks')
        if t.reach > 0 and t.reach >= world.cfg.jump.height:
            raise ConfigError('[tree] reach must be below [jump] height, or no apple can be taken')
        if t.home and world.cfg.crop.capacity < 1:
            raise ConfigError('[tree] home needs [crop] capacity, to carry an apple in')
        self.world = world
        self.seen = np.zeros(world.alive.shape[0])
        self.hops = np.zeros(world.alive.shape)
        self.stored = np.zeros(world.alive.shape, int)

    def reset(self, idx: np.ndarray):
        self.seen[idx] = 0
        self.hops[idx] = 0
        self.stored[idx] = 0

    def step(self):
        w, t = self.world, self.world.cfg.tree
        if t.burrow:
            self.burrow()
        if t.move <= 0:
            return
        ticks = max(round(t.move * w.cfg.tick_hz), 1)
        for a in np.nonzero((w.age > 0) & (w.age % ticks == 0))[0]:
            if scatter.move(w, a, t.trunk):
                for f in np.nonzero(w.food_present[a])[0]:
                    w._grow(a, f)

    def start(self, idx: np.ndarray):
        """Stand each of these arenas' Terrikins round the trunk, `start` m off its edge and facing it, wherever the
        blocks have ended up. An arena with no clear ring in a few tries keeps the nest spawn."""
        w, cfg = self.world, self.world.cfg
        t = cfg.tree
        if t.start <= 0:
            return
        who = np.flatnonzero(~w.spare)
        trunk = cfg.block[t.trunk]
        dist = max(trunk.w, trunk.h) / 2 + cfg.creature.radius + t.start
        room = cfg.arena.size / 2 - cfg.creature.radius
        half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2) + cfg.creature.radius
        # neighbours on the ring have to be a body apart
        chord = 2 * dist * np.sin(np.pi / len(who)) if len(who) > 1 else np.inf
        arenas, creatures, at = [], [], []
        for a in idx:
            middle = w.physics.block_pos[a, t.trunk]
            for _ in range(TRIES):
                angle = w.rng.uniform(0, 2 * np.pi) + np.arange(len(who)) / len(who) * 2 * np.pi
                spots = middle + dist * np.stack([np.cos(angle), np.sin(angle)], -1)
                clear = (np.abs(spots) <= room).all() and chord >= 2 * cfg.creature.radius
                clear = clear and all(not w._on_block(a, s, half) for s in spots)
                clear = clear and (np.hypot(*(spots[:, None] - w.nests[None]).transpose(2, 0, 1))
                                   > cfg.colonies.nest_radius + cfg.creature.radius).all()
                if clear:
                    w.heading[a, who] = (angle + 2 * np.pi) % (2 * np.pi) - np.pi
                    arenas += [a] * len(who)
                    creatures += list(who)
                    at += list(spots)
                    break
        if arenas:
            w.physics.revive(arenas, creatures, np.array(at))

    def burrow(self):
        """Whoever unloaded an apple at home this tick goes down into the nest and comes back up at its middle, turned
        any way, so where it came in and which way it faced say nothing of where the tree is: only its notes can."""
        w = self.world
        down = (w.stored > self.stored) & w.alive
        self.stored = w.stored.copy()
        if not down.any():
            return
        a, c = np.nonzero(down)
        w.heading[a, c] = w.rng.uniform(-np.pi, np.pi, len(a))
        w.physics.revive(a, c, w.nests[w.colony[c]])

    def reaching(self) -> np.ndarray:
        """Who is high enough to take an apple, and has room for it when apples go home, (arenas, creatures)."""
        w = self.world
        up = w.alive & (w.z >= w.cfg.tree.reach)
        return up & (w.crop < w.cfg.crop.capacity) if w.cfg.tree.home else up

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
        now = (w.stored if t.home else w.meals).sum(1).astype(float)
        out = (now - self.seen)[:, None] * t.points * alive - (w.jumps - self.hops) * t.hop
        self.seen, self.hops = now, w.jumps.astype(float)
        return out
