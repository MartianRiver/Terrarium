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
#
# With nights on ([night], night.py), the food standing at nightfall goes and
# none grows back until dawn, and the dark is cold: it drains energy faster,
# except in the nest or close to nestmates.
#
# Moving costs energy: thrust, turning (by its square, so steering is cheap and
# spinning isn't) and sprinting, a burst of speed with a cooldown ([sprint]),
# chosen like unload and eat.
#
# With [grab] on, a creature can take hold of a block it touches and drag it
# about, paying a little energy a second while it holds on. A yes grips for a
# couple of seconds, so a grab is something tried now and then that lasts.

import numpy as np

from . import night
from .smell import Field
from .config import Config, ConfigError
from .log import Logger
from .physics import Physics

log = Logger('world')

PLACE_TRIES = 200
# a ground-jelly slot with nothing in it; food that grows has a regrow timer instead
EMPTY = -1


def box_gap(points: np.ndarray, b) -> np.ndarray:
    """How far each of points (n, 2) is from block b where it started (0 inside it)."""
    d = points - (b.x, b.y)
    cos, sin = np.cos(b.angle), np.sin(b.angle)
    x, y = d[:, 0] * cos + d[:, 1] * sin, -d[:, 0] * sin + d[:, 1] * cos
    return np.hypot(np.maximum(np.abs(x) - b.w / 2, 0), np.maximum(np.abs(y) - b.h / 2, 0))


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
        # ticks since the arena last started, and the time of day (s) it started at: 0 is dawn
        self.age = np.zeros(arenas, int)
        self.clock = np.zeros(arenas)
        # it's night in the arena: no food grows
        self.dark = np.zeros(arenas, bool)
        self.episode_ticks = round(cfg.episode.seconds * cfg.tick_hz)
        self.physics = Physics(cfg, pos)

        # ids the viewer keys on: blocks keep theirs, food gets a new one each time it regrows, and a creature
        # hatched in a lost one's place gets a new one too
        self.creature_id = np.tile(np.arange(1, n + 1), (arenas, 1))
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
        # ticks left of each creature's sprint, and of its rest before it can sprint again
        self.sprinting = np.zeros((arenas, n), int)
        self.resting = np.zeros((arenas, n), int)
        # energy each has spent moving (thrust, turn, sprint) since its arena started
        self.spent = np.zeros((arenas, n))
        self.holding = np.zeros((arenas, n), bool)
        # ticks the grip lasts for after the last yes to grab
        self.gripping = np.zeros((arenas, n), int)
        # ticks until the egg laid in a lost creature's place hatches (0: none), and each colony's hatchlings
        self.egg = np.zeros((arenas, n), int)
        self.hatched = np.zeros((arenas, len(self.nests)), int)
        # blocks one creature can drag (the vault's doors)
        self.doors = [k for k, b in enumerate(cfg.block) if cfg.grab.on and b.mass * cfg.ground.friction < cfg.grab.grip]
        self.smell = Field(cfg.smell, arenas, cfg.arena.size, cfg.block, self.doors) if cfg.smell.on else None

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
            gap = box_gap(self.nests, b)
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
        self.dark[idx] = False
        self.meals[idx] = 0
        self.crop[idx] = self.cfg.crop.start
        self.fed[idx] = 0
        self.store[idx] = 0
        self.stored[idx] = 0
        self.jelly[idx] = 0
        self.sprinting[idx] = 0
        self.resting[idx] = 0
        self.spent[idx] = 0
        self.holding[idx] = False
        self.gripping[idx] = 0
        self.egg[idx] = 0
        self.hatched[idx] = 0
        self.creature_id[idx] = np.arange(1, len(self.colony) + 1)
        if self.smell:
            self.smell.reset(idx)
        self.food_regrow[idx, :self.wild] = 0
        self.food_regrow[idx, self.wild:] = EMPTY
        for a in idx:
            self._place_patches(a)
            for f in range(self.wild):
                self._grow(a, f)
        log.debug('arenas reset', tick=self.tick, count=len(idx))

    def step(self, actions: np.ndarray):
        """actions (arenas, creatures, k): thrust and turn, then unload, eat, sprint and grab (yes when above 0), as
        many of those as k has room for."""
        cfg, c, s, g = self.cfg, self.cfg.creature, self.cfg.sprint, self.cfg.grab
        # the dead don't move
        actions = np.clip(actions, -1, 1) * self.alive[..., None]
        thrust, turn = actions[..., 0], actions[..., 1]
        unload, eat, sprint, grab = ((actions[..., k] > 0) & self.alive if actions.shape[-1] > k
                                     else np.zeros_like(self.alive) for k in (2, 3, 4, 5))
        if s.on:
            go = sprint & (self.sprinting == 0) & (self.resting == 0)
            self.sprinting[go] = round(s.seconds * cfg.tick_hz)
        bursting = self.sprinting > 0

        self.heading = self.heading + turn * c.turn_rate * cfg.dt
        self.heading = (self.heading + np.pi) % (2 * np.pi) - np.pi
        speed = (np.where(thrust >= 0, thrust * np.where(bursting, s.speed, 1.0), thrust * c.reverse)
                 * c.max_speed * (1 - cfg.crop.slow * self.crop))
        target = np.stack([np.cos(self.heading), np.sin(self.heading)], -1) * speed[..., None]
        # the force that closes this share of the gap to the wanted velocity in one tick, if nothing's in the way
        change = (target - self.vel) * min(1.0, c.accel * cfg.dt)
        if g.on:
            self.gripping[grab] = round(g.seconds * cfg.tick_hz)
            self.holding = self.physics.grab(self.gripping > 0, g.reach, g.grip)
            np.maximum(self.gripping - 1, 0, out=self.gripping)
        self.physics.step(change * (c.mass / cfg.dt))

        e = cfg.energy
        # a sprint costs by how hard it runs: standing still through one is free
        effort = (e.move * np.abs(thrust) + e.turn * turn * turn + s.energy * bursting * np.maximum(thrust, 0)
                  + g.energy * self.holding) * cfg.dt
        self.spent += effort
        self.energy = np.clip(self.energy - effort - (e.drain + self._cold()) * cfg.dt, 0, 1)
        self.sprinting[bursting] -= 1
        np.maximum(self.resting - 1, 0, out=self.resting)
        self.resting[bursting & (self.sprinting == 0)] = round(s.cooldown * cfg.tick_hz)
        self._nightfall()
        self._regrow()
        # eating on the tick it would have run out still saves it
        self._eat()
        self._unload(unload)
        self._feed(eat)
        if self.smell:
            self.smell.step(self.food_pos, self.food_present, self.block_pos, self.block_angle)
        dying = self.alive & (self.energy <= 0)
        if dying.any():
            self.alive &= ~dying
            self.sprinting[dying] = 0
            self.holding[dying] = False
            self.gripping[dying] = 0
            self.physics.remove(dying)
            log.debug('creatures died', tick=self.tick, count=int(dying.sum()))
        if cfg.hatch.on:
            self._hatch()
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

    def _hatch(self):
        h = self.cfg.hatch
        tended = np.stack([self.alive[:, self.colony == c].any(1) for c in range(len(self.nests))], 1)
        # an egg needs someone left to tend it
        self.egg[~tended[:, self.colony]] = 0
        due = self.egg == 1
        np.maximum(self.egg - 1, 0, out=self.egg)
        if due.any():
            self._born(due)
        for c in range(len(self.nests)):
            # one egg a tick per colony, in its lowest empty slot
            empty = (self.colony == c) & ~self.alive & (self.egg == 0)
            lays = np.flatnonzero(tended[:, c] & empty.any(1) & (self.store[:, c] >= max(h.threshold, h.cost)))
            if len(lays):
                self.egg[lays, empty[lays].argmax(1)] = max(1, round(h.seconds * self.cfg.tick_hz))
                self.store[lays, c] -= h.cost

    def _born(self, due: np.ndarray):
        """Hatchlings in these (arenas, creatures) slots, somewhere in their own nest."""
        a, i = np.nonzero(due)
        angle = self.rng.uniform(0, 2 * np.pi, len(a))
        r = self.cfg.colonies.nest_radius / 2 * np.sqrt(self.rng.uniform(size=len(a)))
        pos = self.nests[self.colony[i]] + np.stack([np.cos(angle), np.sin(angle)], -1) * r[:, None]
        self.physics.revive(a, i, pos)
        self.heading[a, i] = self.rng.uniform(-np.pi, np.pi, len(a))
        self.energy[a, i] = self.cfg.energy.start
        self.alive[a, i] = True
        self.crop[a, i] = 0
        self.sprinting[a, i] = self.resting[a, i] = self.gripping[a, i] = 0
        np.add.at(self.hatched, (a, self.colony[i]), 1)
        for k, j in zip(a, i):
            self.creature_id[k, j] = self.next_id[k]
            self.next_id[k] += 1
        log.debug('creatures hatched', tick=self.tick, count=len(a))

    def smelled(self) -> tuple[np.ndarray, ...]:
        """How strong the smell of food is where each creature stands (0 to 1), and which way off its heading it
        gets stronger (sin, cos); all 0 with smell off."""
        if not self.smell:
            return tuple(np.zeros_like(self.energy) for _ in range(3))
        return self.smell.sense(self.pos, self.heading)

    def light(self) -> np.ndarray:
        """How light it is in each arena, 1 by day and 0 at night, (arenas,)."""
        return night.light(self.age / self.cfg.tick_hz + self.clock, self.cfg.night)

    def _cold(self) -> np.ndarray | float:
        """Energy per second the dark takes, on top of the drain, (arenas, creatures)."""
        n = self.cfg.night
        if not n.on or n.cold <= 0:
            return 0.0
        kept = night.warmth(self.pos, self.alive, self.colony, self.nest_at() == self.colony, n)
        return n.cold * (1 - self.light())[:, None] * (1 - kept)

    def _nightfall(self):
        """The food standing where night has just fallen goes, to grow back after dawn."""
        dark = night.dark(self.age / self.cfg.tick_hz + self.clock, self.cfg.night)
        fell = dark & ~self.dark
        self.dark = dark
        if not fell.any():
            return
        standing = (self.food_regrow[:, :self.wild] == 0) & fell[:, None]
        hz = self.cfg.tick_hz
        lo, hi = round(self.cfg.food.regrow_min * hz), round(self.cfg.food.regrow_max * hz)
        self.food_regrow[:, :self.wild][standing] = self.rng.integers(lo, hi + 1, int(standing.sum()))
        log.debug('night fell', tick=self.tick, arenas=int(fell.sum()), food=int(standing.sum()))

    def _regrow(self):
        # nothing grows at night
        growing = (self.food_regrow > 0) & ~self.dark[:, None]
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
            middle = p < self.cfg.food.middle
            self.patch_pos[a, p] = 0 if middle else self._open_ground(a, margin=self.cfg.food.patch_radius)

    def _open_ground(self, a, around=None, margin=0.0):
        """A random spot clear of walls, nests and blocks: anywhere, or within patch_radius of around."""
        cfg = self.cfg
        room = cfg.arena.size / 2 - cfg.food.clearance - margin
        nest_gap = cfg.colonies.nest_radius + cfg.food.clearance
        half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2) + cfg.food.radius

        def pick():
            if around is None:
                return self.rng.uniform(-room, room, 2)
            r, t = cfg.food.patch_radius * np.sqrt(self.rng.uniform()), self.rng.uniform(0, 2 * np.pi)
            return around + r * np.array([np.cos(t), np.sin(t)])

        p = pick()
        for _ in range(PLACE_TRIES):
            inside = (np.abs(p) <= room).all()
            near_nest = (np.hypot(*(self.nests - p).T) < nest_gap).any()
            near_block = len(half) and self._on_block(a, p, half)
            if inside and not near_nest and not near_block:
                return p
            p = pick()
        log.warn('no open ground found, placing food anyway', arena=int(a), tries=PLACE_TRIES)
        return p

    def touching_block(self) -> np.ndarray:
        """(arenas, creatures): who has a block within grab's reach."""
        if not self.cfg.grab.on:
            return np.zeros_like(self.alive)
        return self.physics.near_block(self.cfg.grab.reach) & self.alive

    def _on_block(self, a, p, half):
        # in each block's own frame, so a long thin one keeps food off itself and not off a circle around it
        d = p - self.physics.block_pos[a]
        cos, sin = np.cos(self.physics.block_angle[a]), np.sin(self.physics.block_angle[a])
        x, y = d[:, 0] * cos + d[:, 1] * sin, -d[:, 0] * sin + d[:, 1] * cos
        return ((np.abs(x) < half[:, 0]) & (np.abs(y) < half[:, 1])).any()
