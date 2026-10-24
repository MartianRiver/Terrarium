# The world: colonies of creatures around their nests, food that's eaten and
# regrows, pushable blocks, walls. Runs many independent arenas at once; every
# array is (arenas, ...) and an action is (thrust, turn) per creature in [-1, 1].
# A creature dies when its energy runs out, and its body leaves the world where
# it fell: nothing bumps into it or sees it. An arena has ended once everyone in
# it is dead or its episode is up, and the caller starts it over with reset().
#
# Food a creature eats past full goes into its crop, like an ant's social
# stomach, and weighs it down. Two more actions, unload and eat, are the
# creature's to choose: unloading turns the crop into jelly, into the store of
# the nest it's in or, outside one, onto the ground for anyone to eat; eating
# takes from its crop once there's room for a whole food (the line that decides
# stomach or crop), or in its own nest from the store, which only a hungry one
# ([jelly] hunger) can. Jelly gives back less than the food it came from.

import numpy as np

from .config import Config, ConfigError
from .log import Logger
from .physics import Physics

log = Logger('world')

PLACE_TRIES = 200
# a ground-jelly slot with nothing in it; food that grows has a regrow timer instead
EMPTY = -1


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

        pos, self.heading = self._spawn(arenas)
        self.energy = np.full((arenas, n), cfg.energy.start)
        self.alive = np.ones((arenas, n), bool)
        # ticks since the arena last started
        self.age = np.zeros(arenas, int)
        self.episode_ticks = round(cfg.episode.seconds * cfg.tick_hz)
        self.physics = Physics(cfg, pos)

        # ids the viewer keys on: creatures and blocks keep theirs, food gets a new one each time it regrows
        self.creature_id = np.arange(1, n + 1)
        self.block_id = np.arange(n + 1, n + len(cfg.block) + 1)
        self.next_id = np.full(arenas, n + len(cfg.block) + 1)
        self.patch_pos = np.zeros((arenas, cfg.food.patches, 2))
        for a in range(arenas):
            self._place_patches(a)
        # the food that grows, then a slot for every jelly the creatures could leave on the ground at once
        self.wild = cfg.food.count
        slots = self.wild + n * cfg.crop.capacity
        self.food_pos = np.zeros((arenas, slots, 2))
        self.food_id = np.zeros((arenas, slots), int)
        # ticks until a food grows back; 0 means it's there
        self.food_regrow = np.zeros((arenas, slots), int)
        self.food_regrow[:, self.wild:] = EMPTY
        for a in range(arenas):
            for f in range(self.wild):
                self._grow(a, f)
        self.eaten = 0
        # food each creature has picked up where it grew (eaten or carried) since its arena started
        self.meals = np.zeros((arenas, n), int)
        self.crop = np.full((arenas, n), cfg.crop.start)
        # energy each creature has got from food (not jelly) since its arena started
        self.fed = np.zeros((arenas, n))
        # jelly in each colony's store, food unloaded into it and jelly eaten from it per creature
        self.store = np.zeros((arenas, len(self.nests)), int)
        self.stored = np.zeros((arenas, n), int)
        self.jelly = np.zeros((arenas, n), int)

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

    @property
    def ended(self):
        return ~self.alive.any(1) | (self.age >= self.episode_ticks)

    def _check_layout(self):
        # the spawn ring turns randomly, so every block has to be clear of the whole ring
        if not 0 <= self.cfg.crop.start <= self.cfg.crop.capacity:
            raise ConfigError(f'crop.start {self.cfg.crop.start} is more than a crop holds')
        reach = self.cfg.colonies.spawn_ring + self.cfg.creature.radius
        if (np.abs(self.nests) + reach > self.cfg.arena.size / 2).any():
            raise ConfigError(f'colonies.spawn_ring {self.cfg.colonies.spawn_ring} reaches past the walls')
        for i, b in enumerate(self.cfg.block):
            gap = np.hypot(*(self.nests - (b.x, b.y)).T) - np.hypot(b.w, b.h) / 2
            if (gap <= reach).any():
                raise ConfigError(f'block[{i}] at ({b.x}, {b.y}) is close enough to a nest for creatures to spawn inside it')

    def _spawn(self, arenas):
        """Each colony on an evenly spaced ring around its nest, turned a random amount per arena."""
        size = self.cfg.colonies.size
        ring = np.arange(size) / size * 2 * np.pi
        turn = self.rng.uniform(0, 2 * np.pi, (arenas, len(self.nests), 1))
        a = (ring + turn).reshape(arenas, -1)
        pos = self.nests[self.colony] + np.stack([np.cos(a), np.sin(a)], -1) * self.cfg.colonies.spawn_ring
        heading = self.rng.uniform(-np.pi, np.pi, a.shape)
        return pos, heading

    def reset(self, arenas: np.ndarray):
        """Start the arenas in this mask over: creatures respawn, blocks go back, all the food regrows somewhere new."""
        idx = np.flatnonzero(arenas)
        if not len(idx):
            return
        pos, heading = self._spawn(len(idx))
        self.heading[idx] = heading
        self.physics.place(idx, pos)
        self.energy[idx] = self.cfg.energy.start
        self.alive[idx] = True
        self.age[idx] = 0
        self.meals[idx] = 0
        self.crop[idx] = self.cfg.crop.start
        self.fed[idx] = 0
        self.store[idx] = 0
        self.stored[idx] = 0
        self.jelly[idx] = 0
        self.food_regrow[idx, :self.wild] = 0
        self.food_regrow[idx, self.wild:] = EMPTY
        for a in idx:
            self._place_patches(a)
            for f in range(self.wild):
                self._grow(a, f)
        log.debug('arenas reset', tick=self.tick, count=len(idx))

    def step(self, actions: np.ndarray):
        """actions (arenas, creatures, k): thrust and turn, then unload and eat (yes when above 0) if k is 4."""
        cfg, c = self.cfg, self.cfg.creature
        # the dead don't move
        actions = np.clip(actions, -1, 1) * self.alive[..., None]
        thrust, turn = actions[..., 0], actions[..., 1]
        unload, eat = ((actions[..., k] > 0) & self.alive if actions.shape[-1] > k else np.zeros_like(self.alive)
                       for k in (2, 3))

        self.heading = self.heading + turn * c.turn_rate * cfg.dt
        self.heading = (self.heading + np.pi) % (2 * np.pi) - np.pi
        speed = np.where(thrust >= 0, thrust, thrust * c.reverse) * c.max_speed * (1 - cfg.crop.slow * self.crop)
        target = np.stack([np.cos(self.heading), np.sin(self.heading)], -1) * speed[..., None]
        # the force that closes this share of the gap to the wanted velocity in one tick, if nothing's in the way
        change = (target - self.vel) * min(1.0, c.accel * cfg.dt)
        self.physics.step(change * (c.mass / cfg.dt))

        e = cfg.energy
        self.energy = np.clip(self.energy - (e.drain + e.move * np.abs(thrust)) * cfg.dt, 0, 1)
        self._regrow()
        # eating on the tick it would have run out still saves it
        self._eat()
        self._unload(unload)
        self._feed(eat)
        dying = self.alive & (self.energy <= 0)
        if dying.any():
            self.alive &= ~dying
            self.physics.remove(dying)
            log.debug('creatures died', tick=self.tick, count=int(dying.sum()))
        self.age += 1
        self.tick += 1

    def _eat(self):
        cfg = self.cfg
        reach = cfg.creature.radius + cfg.food.radius
        # x and y apart: summing over a length-2 last axis is much slower in numpy
        dx = self.pos[:, :, None, 0] - self.food_pos[:, None, :, 0]
        dy = self.pos[:, :, None, 1] - self.food_pos[:, None, :, 1]
        hungry = self.energy <= 1 - cfg.energy.food
        # one too full to eat food and with no room in its crop walks over it; jelly on the ground is only
        # eaten, by one with room for it
        takes = self.alive & (hungry | (self.crop < cfg.crop.capacity))
        wants_jelly = self.alive & (self.energy <= 1 - cfg.jelly.energy)
        takes = np.where(np.arange(self.food_pos.shape[1]) < self.wild, takes[..., None], wants_jelly[..., None])
        touching = (dx * dx + dy * dy < reach * reach) & self.food_present[:, None] & takes
        eaten = touching.any(1)
        if not eaten.any():
            return
        # when two creatures reach the same food on one tick, the lower index gets it
        arena, food = np.nonzero(eaten)
        who = touching.argmax(1)[arena, food]
        wild = food < self.wild
        eats = hungry[arena, who] | ~wild
        before = self.energy.copy()
        np.add.at(self.energy, (arena[eats], who[eats]), np.where(wild, cfg.energy.food, cfg.jelly.energy)[eats])
        np.clip(self.energy, 0, 1, out=self.energy)
        self.fed += self.energy - before
        np.add.at(self.crop, (arena[~eats], who[~eats]), 1)
        np.add.at(self.meals, (arena[wild], who[wild]), 1)
        # two foods on one tick can overfill a crop; the extra is lost
        np.minimum(self.crop, cfg.crop.capacity, out=self.crop)
        hz = self.cfg.tick_hz
        lo, hi = round(self.cfg.food.regrow_min * hz), round(self.cfg.food.regrow_max * hz)
        self.food_regrow[arena, food] = np.where(wild, self.rng.integers(lo, hi + 1, len(arena)), EMPTY)
        self.eaten += len(arena)
        log.trace('food eaten', tick=self.tick, count=len(arena))

    def nest_at(self) -> np.ndarray:
        """Which nest each creature is standing in, -1 for none, (arenas, creatures)."""
        d = self.pos[:, :, None] - self.nests                                 # A,N,C,2
        inside = d[..., 0] ** 2 + d[..., 1] ** 2 < self.cfg.colonies.nest_radius ** 2
        return np.where(inside.any(-1), inside.argmax(-1), -1)

    def _unload(self, unload: np.ndarray):
        """The crop as jelly into the store of the nest it's in (a rival's too), or onto the ground outside one."""
        unload = unload & (self.crop > 0)
        if not unload.any():
            return
        nest = self.nest_at()
        load = np.where(unload, self.crop, 0)
        for c in range(len(self.nests)):
            self.store[:, c] += np.where(nest == c, load, 0).sum(1)
        self.stored += np.where(nest == self.colony, load, 0)
        for a, i in zip(*np.nonzero(unload & (nest < 0))):
            self._drop(a, i, load[a, i])
        self.crop[unload] = 0

    def _drop(self, a, i, count):
        cfg = self.cfg
        free = np.flatnonzero(self.food_regrow[a, self.wild:] == EMPTY)[:count] + self.wild
        # just behind it, so it doesn't eat it straight back
        back = cfg.creature.radius + cfg.food.radius + 0.05
        facing = np.array([np.cos(self.heading[a, i]), np.sin(self.heading[a, i])])
        side = np.array([-facing[1], facing[0]])
        room = cfg.arena.size / 2 - cfg.food.radius
        for k, f in enumerate(free):
            spot = self.pos[a, i] - facing * (back + 0.3 * (k // 2)) + side * 0.3 * (k % 2 - 0.5) * (count > 1)
            self.food_pos[a, f] = np.clip(spot, -room, room)
            self.food_regrow[a, f] = 0
            self.food_id[a, f] = self.next_id[a]
            self.next_id[a] += 1

    def _feed(self, eat: np.ndarray):
        """Eating chosen: from its crop if it carries any and has room, else in its own nest from the store, if it's hungry."""
        cfg = self.cfg
        own = eat & (self.crop > 0) & (self.energy <= 1 - cfg.energy.food)
        self.energy += cfg.energy.food * own
        self.fed += cfg.energy.food * own
        self.crop[own] -= 1
        wants = eat & (self.crop == 0) & (self.nest_at() == self.colony) & (self.energy < cfg.jelly.hunger)
        for c in range(len(self.nests)):
            # one jelly each, lowest index first, while the store lasts
            mine = wants & (self.colony == c)
            gets = mine & (np.cumsum(mine, 1) <= self.store[:, c, None])
            self.store[:, c] -= gets.sum(1)
            self.energy[gets] += cfg.jelly.energy
            self.jelly[gets] += 1
        np.clip(self.energy, 0, 1, out=self.energy)

    def _regrow(self):
        growing = self.food_regrow > 0
        self.food_regrow[growing] -= 1
        for a, f in zip(*np.nonzero(growing & (self.food_regrow == 0))):
            self._grow(a, f)

    def _grow(self, a, f):
        patches = self.cfg.food.patches
        self.food_pos[a, f] = self._open_ground(a, self.patch_pos[a, f % patches] if patches else None)
        self.food_id[a, f] = self.next_id[a]
        self.next_id[a] += 1

    def _place_patches(self, a):
        # the centres keep a patch's radius from the walls, so the whole patch is ground food can grow on
        for p in range(self.cfg.food.patches):
            self.patch_pos[a, p] = self._open_ground(a, margin=self.cfg.food.patch_radius)

    def _open_ground(self, a, around=None, margin=0.0):
        """A random spot clear of walls, nests and blocks: anywhere, or within patch_radius of around."""
        cfg = self.cfg
        room = cfg.arena.size / 2 - cfg.food.clearance - margin
        nest_gap = cfg.colonies.nest_radius + cfg.food.clearance
        block_gap = np.array([np.hypot(b.w, b.h) / 2 for b in cfg.block]) + cfg.food.radius

        def pick():
            if around is None:
                return self.rng.uniform(-room, room, 2)
            r, t = cfg.food.patch_radius * np.sqrt(self.rng.uniform()), self.rng.uniform(0, 2 * np.pi)
            return around + r * np.array([np.cos(t), np.sin(t)])

        p = pick()
        for _ in range(PLACE_TRIES):
            inside = (np.abs(p) <= room).all()
            near_nest = (np.hypot(*(self.nests - p).T) < nest_gap).any()
            near_block = len(block_gap) and (np.hypot(*(self.physics.block_pos[a] - p).T) < block_gap).any()
            if inside and not near_nest and not near_block:
                return p
            p = pick()
        log.warn('no open ground found, placing food anyway', arena=int(a), tries=PLACE_TRIES)
        return p
