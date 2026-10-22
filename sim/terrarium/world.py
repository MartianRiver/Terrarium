# The world: colonies of creatures around their nests, food that's eaten and
# regrows, pushable blocks, walls. Runs many independent arenas at once; every
# array is (arenas, ...) and an action is (thrust, turn) per creature in [-1, 1].

import numpy as np

from .config import Config, ConfigError
from .log import Logger
from .physics import Physics

log = Logger('world')

PLACE_TRIES = 200


class World:
    def __init__(self, cfg: Config, arenas: int = 1, seed: int = 0):
        self.cfg = cfg
        self.arenas = arenas
        self.rng = np.random.default_rng(seed)
        self.tick = 0

        col = cfg.colonies
        half = cfg.arena.size / 2
        angles = np.arange(col.count) / col.count * 2 * np.pi + np.pi / 2
        self.nests = np.stack([np.cos(angles), np.sin(angles)], -1) * half * col.nest_distance
        self.colony = np.repeat(np.arange(col.count), col.size)
        n = len(self.colony)
        self._check_layout()

        pos, self.heading = self._spawn()
        self.energy = np.full((arenas, n), cfg.energy.start)
        self.physics = Physics(cfg, pos)

        # ids the viewer keys on: creatures and blocks keep theirs, food gets a new one each time it regrows
        self.creature_id = np.arange(1, n + 1)
        self.block_id = np.arange(n + 1, n + len(cfg.block) + 1)
        self.next_id = np.full(arenas, n + len(cfg.block) + 1)
        self.food_pos = np.zeros((arenas, cfg.food.count, 2))
        self.food_id = np.zeros((arenas, cfg.food.count), int)
        # ticks until a food grows back; 0 means it's there
        self.food_regrow = np.zeros((arenas, cfg.food.count), int)
        for a in range(arenas):
            for f in range(cfg.food.count):
                self._grow(a, f)
        self.eaten = 0

        log.info('world created', arenas=arenas, creatures=n, food=cfg.food.count, blocks=len(cfg.block), seed=seed)

    @property
    def pos(self):
        return self.physics.pos

    @property
    def vel(self):
        return self.physics.vel

    @property
    def block_pos(self):
        return self.physics.block_pos

    @property
    def block_angle(self):
        return self.physics.block_angle

    @property
    def food_present(self):
        return self.food_regrow == 0

    def _check_layout(self):
        # the spawn ring turns randomly, so every block has to be clear of the whole ring
        reach = self.cfg.colonies.spawn_ring + self.cfg.creature.radius
        for i, b in enumerate(self.cfg.block):
            gap = np.hypot(*(self.nests - (b.x, b.y)).T) - np.hypot(b.w, b.h) / 2
            if (gap <= reach).any():
                raise ConfigError(f'block[{i}] at ({b.x}, {b.y}) is close enough to a nest for creatures to spawn inside it')

    def _spawn(self):
        """Each colony on an evenly spaced ring around its nest, turned a random amount per arena."""
        size = self.cfg.colonies.size
        ring = np.arange(size) / size * 2 * np.pi
        turn = self.rng.uniform(0, 2 * np.pi, (self.arenas, len(self.nests), 1))
        a = (ring + turn).reshape(self.arenas, -1)
        pos = self.nests[self.colony] + np.stack([np.cos(a), np.sin(a)], -1) * self.cfg.colonies.spawn_ring
        heading = self.rng.uniform(-np.pi, np.pi, a.shape)
        return pos, heading

    def step(self, actions: np.ndarray):
        cfg, c = self.cfg, self.cfg.creature
        actions = np.clip(actions, -1, 1)
        thrust, turn = actions[..., 0], actions[..., 1]

        self.heading = self.heading + turn * c.turn_rate * cfg.dt
        self.heading = (self.heading + np.pi) % (2 * np.pi) - np.pi
        speed = np.where(thrust >= 0, thrust, thrust * c.reverse) * c.max_speed
        target = np.stack([np.cos(self.heading), np.sin(self.heading)], -1) * speed[..., None]
        # the force that closes this share of the gap to the wanted velocity in one tick, if nothing's in the way
        change = (target - self.vel) * min(1.0, c.accel * cfg.dt)
        self.physics.step(change * (c.mass / cfg.dt))

        e = cfg.energy
        self.energy = np.clip(self.energy - (e.drain + e.move * np.abs(thrust)) * cfg.dt, 0, 1)
        self._regrow()
        self._eat()
        self.tick += 1

    def _eat(self):
        reach = self.cfg.creature.radius + self.cfg.food.radius
        # x and y apart: summing over a length-2 last axis is much slower in numpy
        dx = self.pos[:, :, None, 0] - self.food_pos[:, None, :, 0]
        dy = self.pos[:, :, None, 1] - self.food_pos[:, None, :, 1]
        touching = (dx * dx + dy * dy < reach * reach) & self.food_present[:, None]
        eaten = touching.any(1)
        if not eaten.any():
            return
        # when two creatures reach the same food on one tick, the lower index gets it
        arena, food = np.nonzero(eaten)
        who = touching.argmax(1)[arena, food]
        np.add.at(self.energy, (arena, who), self.cfg.energy.food)
        np.clip(self.energy, 0, 1, out=self.energy)
        hz = self.cfg.tick_hz
        lo, hi = round(self.cfg.food.regrow_min * hz), round(self.cfg.food.regrow_max * hz)
        self.food_regrow[arena, food] = self.rng.integers(lo, hi + 1, len(arena))
        self.eaten += len(arena)
        log.trace('food eaten', tick=self.tick, count=len(arena))

    def _regrow(self):
        growing = self.food_regrow > 0
        self.food_regrow[growing] -= 1
        for a, f in zip(*np.nonzero(growing & (self.food_regrow == 0))):
            self._grow(a, f)

    def _grow(self, a, f):
        self.food_pos[a, f] = self._open_ground(a)
        self.food_id[a, f] = self.next_id[a]
        self.next_id[a] += 1

    def _open_ground(self, a):
        """A random spot clear of walls, nests and blocks."""
        cfg = self.cfg
        room = cfg.arena.size / 2 - cfg.food.clearance
        nest_gap = cfg.colonies.nest_radius + cfg.food.clearance
        block_gap = np.array([np.hypot(b.w, b.h) / 2 for b in cfg.block]) + cfg.food.radius
        p = self.rng.uniform(-room, room, 2)
        for _ in range(PLACE_TRIES):
            near_nest = (np.hypot(*(self.nests - p).T) < nest_gap).any()
            near_block = len(block_gap) and (np.hypot(*(self.physics.block_pos[a] - p).T) < block_gap).any()
            if not near_nest and not near_block:
                return p
            p = self.rng.uniform(-room, room, 2)
        log.warn('no open ground found, placing food anyway', arena=int(a), tries=PLACE_TRIES)
        return p
