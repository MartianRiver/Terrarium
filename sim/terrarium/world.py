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
# With [flowers] on, a nectar flower opens now and then by day, rare and rich:
# the first to touch one drinks it all, food's worth several times over (eaten
# or carried like food) and a burst of speed that lasts a few seconds. It closes
# by itself before long, so it's worth hurrying to. With `spots` set, flowers open
# only at a few spots drawn anew each episode: a test of memory, since the spots
# stay put while out of sight.
#
# With [grab] on, a creature can take hold of a block it touches and drag it
# about, paying a little energy a second while it holds on. A yes grips for a
# couple of seconds, so a grab is something tried now and then that lasts.
#
# With [carry] on, a creature can pick up a berry in its jaws and take it
# somewhere, as an ant carries a seed: nothing to do with its crop. A yes to
# carry (after a no) picks up the nearest berry within reach, another puts it
# down again, still a berry, for anyone to eat. Carrying slows it a little and
# costs a little energy. The berry keeps its own place among the food: it's off
# the ground (unseen, unsmelled, not growing back) until it's put down, and one
# that dies carrying drops it where it falls. A block marked `carry` is carried
# the same way when no berry is in reach: lifted out of the world (nothing
# bumps into it, sees it or smells round it) and set down in front, crosswise,
# if the ground there is clear. Blocks too heavy to push can still be carried.
#
# With [young] on, a hatchling is young for a while, as a nest's young are fed
# while they grow: it's slower, everything costs it less, and in its own nest it
# can eat from the store whenever it isn't full, a bite its size (a jelly goes as
# much further as its costs are less), not only when it's hungry.

# where a carried block is, for anything that senses blocks: well off the arena
AWAY = 1e4

import numpy as np

from . import night, tired
from .smell import Field
from .flags import Flags
from .peek import Peek
from .maze import carve, check as check_maze
from .scatter import scatter
from .seek import Seek
from .tag import Tag
from .config import Config, ConfigError
from .log import Logger
from .physics import Physics

log = Logger('world')

PLACE_TRIES = 200
# a ground-jelly slot with nothing in it; food that grows has a regrow timer instead
EMPTY = -1
# a berry in someone's jaws, in place of its regrow timer
CARRIED = -2


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
        self.colony = np.repeat(np.arange(col.count), col.slots)
        # each colony's places past its starting size: empty until it hatches into them
        self.spare = np.tile(np.arange(col.slots) >= col.size, col.count)
        n = len(self.colony)
        self._check_layout()

        pos, self.heading = self._spawn(arenas)
        self.energy = np.where(self.spare, 0.0, np.full((arenas, n), cfg.energy.start))
        self.alive = np.tile(~self.spare, (arenas, 1))
        # places nobody has been in yet this episode, which replays leave out
        self.unborn = np.tile(self.spare, (arenas, 1))
        # ticks since the arena last started, and the time of day (s) it started at: 0 is dawn
        self.age = np.zeros(arenas, int)
        self.clock = np.zeros(arenas)
        # it's night in the arena: no food grows
        self.dark = np.zeros(arenas, bool)
        self.episode_ticks = round(cfg.episode.seconds * cfg.tick_hz)
        self.physics = Physics(cfg, pos)
        self.physics.remove(self.unborn)

        # ids the viewer keys on: blocks keep theirs, food gets a new one each time it regrows, and a hatchling
        # gets the one its egg had
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
        # the ways between rooms in each arena's maze ([arena] maze)
        self.maze_open: list[set] = [set() for _ in range(arenas)]
        if cfg.arena.maze:
            carve(self, np.arange(arenas))
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
        # jelly, in grown Terrikins' bites (the young take smaller ones)
        self.store = np.zeros((arenas, len(self.nests)))
        self.stored = np.zeros((arenas, n), int)
        self.jelly = np.zeros((arenas, n))
        # ticks left of each creature's sprint, and of its rest before it can sprint again
        self.sprinting = np.zeros((arenas, n), int)
        self.resting = np.zeros((arenas, n), int)
        # energy each has spent moving (thrust, turn, sprint) since its arena started
        self.spent = np.zeros((arenas, n))
        self.holding = np.zeros((arenas, n), bool)
        # ticks the grip lasts for after the last yes to grab
        self.gripping = np.zeros((arenas, n), int)
        # ticks until the egg laid in an empty place hatches (0: none), where it lies, its id (the hatchling's
        # too), and each colony's hatchlings
        self.egg = np.zeros((arenas, n), int)
        self.egg_pos = np.zeros((arenas, n, 2))
        self.egg_id = np.zeros((arenas, n), int)
        self.hatched = np.zeros((arenas, len(self.nests)), int)
        # ticks each hatchling has left of being young ([young])
        self.young = np.zeros((arenas, n), int)
        # open nectar flowers: where, ticks until each closes (0: not open), ids, and ticks until the next opens
        fl = cfg.flowers
        self.flower_pos = np.zeros((arenas, fl.count, 2))
        self.flower_left = np.zeros((arenas, fl.count), int)
        self.flower_id = np.zeros((arenas, fl.count), int)
        self.flower_due = self._flower_wait(arenas)
        self.flower_spots = np.zeros((arenas, fl.spots, 2))
        for a in range(arenas):
            self._place_spots(a)
        # ticks left of each creature's nectar boost, and the flowers each has drunk since its arena started
        self.nectar = np.zeros((arenas, n), int)
        # how much go each has left before it tires ([tired]; always 1 with it off)
        self.stamina = np.ones((arenas, n))
        self.drunk = np.zeros((arenas, n), int)
        # the berry each creature carries (its food slot, -1 for none), whether it said yes to carry last tick, and
        # since its arena started: berries picked up, put down at its own nest, and put down ones a nestmate ate,
        # also counted for a hungry nestmate; who put each berry down where it lies, -1 if it grew there
        self.load = np.full((arenas, n), -1)
        self.carry_was = np.zeros((arenas, n), bool)
        # the block each creature carries (-1 for none), and how many it has lifted since its arena started
        self.block_load = np.full((arenas, n), -1)
        self.lifted = np.zeros((arenas, n), int)
        self.carryable = np.array([b.carry for b in cfg.block], bool)
        # ticks a block that swings shut waits on the ground before going back (-1: it isn't waiting)
        self.shut_in = np.full((arenas, len(cfg.block)), -1)
        self.picked = np.zeros((arenas, n), int)
        self.put_home = np.zeros((arenas, n), int)
        self.given = np.zeros((arenas, n), int)
        self.given_hungry = np.zeros((arenas, n), int)
        self.food_by = np.full((arenas, slots), -1)
        # blocks one creature can drag (the vault's doors)
        self.doors = [k for k, b in enumerate(cfg.block) if cfg.grab.on and b.mass * cfg.ground.friction < cfg.grab.grip]
        self.smell = Field(cfg.smell, arenas, cfg.arena.size, cfg.block, self.doors) if cfg.smell.on else None
        self.tag = Tag(self) if cfg.tag.on else None
        self.seek = Seek(self) if cfg.seek.on else None
        self.flags = Flags(self) if cfg.flag.on else None
        self.peek = Peek(self) if cfg.peek.on else None
        if cfg.young.start:
            self.young[:] = np.where(self.spare, 0, round(cfg.young.seconds * cfg.tick_hz))
        if self.tag:
            self.tag.reset(np.arange(arenas))

        log.info('world created', arenas=arenas, creatures=n, food=cfg.food.count, blocks=len(cfg.block), seed=seed)

    @property
    def pos(self):
        return self.physics.pos

    @property
    def vel(self):
        return self.physics.vel

    @property
    def block_pos(self):
        if not self.blocks_carried.any():
            return self.physics.block_pos
        p = self.physics.block_pos.copy()
        p[self.blocks_carried] = AWAY
        return p

    @property
    def blocks_carried(self):
        """(arenas, blocks): which blocks are being carried."""
        out = np.zeros(self.physics.block_pos.shape[:2], bool)
        a, i = np.nonzero(self.block_load >= 0)
        out[a, self.block_load[a, i]] = True
        return out

    @property
    def block_angle(self):
        return self.physics.block_angle

    @property
    def food_present(self):
        return self.food_regrow == 0

    @property
    def food_seen(self):
        """Food rays can see: all that's there, but peekaboo's berry once it hides."""
        return self.food_present & ~self.peek.hidden[:, None] if self.peek else self.food_present

    @property
    def flowers_open(self):
        return self.flower_left > 0

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
        # smell's walls and doors that swing shut go by where blocks are set, not where they're scattered to
        if self.cfg.arena.scatter and (self.cfg.smell.on or any(b.carry or b.shut for b in self.cfg.block)):
            raise ConfigError('arena.scatter is for blocks that stay put: not with smell, carry or shut')
        if self.cfg.arena.maze:
            check_maze(self.cfg)

    def _spawn(self, arenas):
        """Each colony on an evenly spaced ring around its nest, turned a random amount per arena."""
        size = self.cfg.colonies.slots
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
        if self.cfg.arena.scatter:
            scatter(self, idx)
        if self.cfg.arena.maze:
            carve(self, idx)
        self.energy[idx] = np.where(self.spare, 0.0, self.cfg.energy.start)
        self.alive[idx] = ~self.spare
        self.unborn[idx] = self.spare
        if self.spare.any():
            gone = np.zeros_like(self.alive)
            gone[idx] = self.spare
            self.physics.remove(gone)
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
        self.young[idx] = np.where(self.spare, 0, round(self.cfg.young.seconds * self.cfg.tick_hz)) if self.cfg.young.start else 0
        self.flower_left[idx] = 0
        self.flower_due[idx] = self._flower_wait(len(idx))
        self.nectar[idx] = 0
        self.stamina[idx] = 1
        self.drunk[idx] = 0
        self.load[idx] = -1
        self.carry_was[idx] = False
        self.block_load[idx] = -1
        self.shut_in[idx] = -1
        self.lifted[idx] = 0
        self.picked[idx] = 0
        self.put_home[idx] = 0
        self.given[idx] = 0
        self.given_hungry[idx] = 0
        self.food_by[idx] = -1
        self.creature_id[idx] = np.arange(1, len(self.colony) + 1)
        if self.smell:
            self.smell.reset(idx)
        if self.tag:
            self.tag.reset(idx)
        if self.seek:
            self.seek.reset(idx)
        if self.flags:
            self.flags.reset(idx)
        if self.peek:
            self.peek.reset(idx)
        self.food_regrow[idx, :self.wild] = 0
        self.food_regrow[idx, self.wild:] = EMPTY
        for a in idx:
            self._place_patches(a)
            self._place_spots(a)
            for f in range(self.wild):
                self._grow(a, f)
        log.debug('arenas reset', tick=self.tick, count=len(idx))

    def step(self, actions: np.ndarray):
        """actions (arenas, creatures, k): thrust and turn, then unload, eat, sprint, grab and carry (yes when above
        0), as many of those as k has room for."""
        cfg, c, s, g = self.cfg, self.cfg.creature, self.cfg.sprint, self.cfg.grab
        # the dead don't move
        actions = np.clip(actions, -1, 1) * self.alive[..., None]
        if self.seek:
            actions = self.seek.hold(actions)
        thrust, turn = actions[..., 0], actions[..., 1]
        unload, eat, sprint, grab, carry = ((actions[..., k] > 0) & self.alive if actions.shape[-1] > k
                                            else np.zeros_like(self.alive) for k in (2, 3, 4, 5, 6))
        if s.on:
            go = sprint & (self.sprinting == 0) & (self.resting == 0)
            self.sprinting[go] = round(s.seconds * cfg.tick_hz)
        bursting = self.sprinting > 0

        self.heading = self.heading + turn * c.turn_rate * cfg.dt
        self.heading = (self.heading + np.pi) % (2 * np.pi) - np.pi
        laden = (self.load >= 0) | (self.block_load >= 0)
        young = self.young > 0
        chasing = self.tag.mask() if self.tag else np.zeros_like(young)
        top = (c.max_speed * np.where(young, cfg.young.speed, 1.0) * np.where(chasing, cfg.tag.speed, 1.0)
               * np.where(self.nectar > 0, cfg.flowers.speed, 1.0) * (1 - cfg.crop.slow * self.crop) * (1 - cfg.carry.slow * laden)
               * tired.speed(self))
        speed = np.where(thrust >= 0, thrust * np.where(bursting, s.speed, 1.0), thrust * c.reverse) * top
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
        # the young pay a share of every cost
        share = np.where(young, cfg.young.energy, 1.0)
        effort = (e.move * np.abs(thrust) + e.turn * turn * turn + s.energy * bursting * np.maximum(thrust, 0)
                  + g.energy * self.holding + cfg.carry.energy * laden) * cfg.dt * share
        self.spent += effort
        self.energy = np.clip(self.energy - effort - (e.drain + self._cold()) * cfg.dt * share, 0, 1)
        if cfg.tired.on:
            tired.tire(self, thrust, bursting)
        np.maximum(self.young - 1, 0, out=self.young)
        self.sprinting[bursting] -= 1
        np.maximum(self.resting - 1, 0, out=self.resting)
        np.maximum(self.nectar - 1, 0, out=self.nectar)
        self.resting[bursting & (self.sprinting == 0)] = round(s.cooldown * cfg.tick_hz)
        self._nightfall()
        self._regrow()
        if cfg.flowers.on:
            self._bloom()
        if cfg.carry.on:
            self._carry(carry)
            if (self.shut_in >= 0).any():
                self._swing_shut()
        if self.tag:
            self.tag.step()
        if self.seek:
            self.seek.step()
        if self.flags:
            self.flags.step(unload)
        if self.peek:
            self.peek.step()
        # eating on the tick it would have run out still saves it
        self._eat()
        if cfg.flowers.on:
            self._drink()
        self._unload(unload)
        self._feed(eat)
        if self.smell:
            self.smell.step(self.food_pos, self.food_present, self.block_pos, self.block_angle)
        dying = self.alive & (self.energy <= 0)
        if dying.any():
            self.alive &= ~dying
            self.sprinting[dying] = 0
            self.nectar[dying] = 0
            self.holding[dying] = False
            self.gripping[dying] = 0
            self.young[dying] = 0
            for a, i in zip(*np.nonzero(dying & (self.load >= 0))):
                self._put_down(a, i, self.pos[a, i])
            for a, i in zip(*np.nonzero(dying & (self.block_load >= 0))):
                # where it falls if there's room, else in front, else where it falls anyway
                if not self._set_block_down(a, i):
                    k = self.block_load[a, i]
                    self.physics.set_down(a, k, self.pos[a, i], self.heading[a, i], anyway=True)
                    self._wait_to_shut(a, k)
                    self.block_load[a, i] = -1
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
        self._credit(arena, food, who)
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

    def _carry(self, carry: np.ndarray):
        """A yes after a no puts down the berry carried, or picks up the nearest one within reach; the lower
        index first when two reach for the same one."""
        want = carry & ~self.carry_was
        self.carry_was = carry
        if not want.any():
            return
        cfg = self.cfg
        reach = cfg.creature.radius + cfg.food.radius + cfg.carry.reach
        facing = np.stack([np.cos(self.heading), np.sin(self.heading)], -1)
        for a, i in zip(*np.nonzero(want)):
            if self.load[a, i] >= 0:
                # just in front of it, where an ant sets down what it carries
                self._put_down(a, i, self.pos[a, i] + facing[a, i] * (cfg.creature.radius + cfg.food.radius))
                continue
            if self.block_load[a, i] >= 0:
                self._set_block_down(a, i)
                continue
            d = np.hypot(*(self.food_pos[a, :self.wild] - self.pos[a, i]).T)
            d[~self.food_present[a, :self.wild]] = np.inf
            # argmin of nothing, in a world without food, is an error, not a miss
            f = int(d.argmin()) if len(d) else -1
            if f >= 0 and d[f] < reach:
                self.food_regrow[a, f] = CARRIED
                self.load[a, i] = f
                self.picked[a, i] += 1
            elif self.carryable.any():
                k = self.physics.nearest_block(a, i, cfg.carry.reach)
                if k >= 0 and self.carryable[k]:
                    self.physics.lift(a, k)
                    self.block_load[a, i] = k
                    self.shut_in[a, k] = -1
                    self.lifted[a, i] += 1

    def _set_block_down(self, a, i) -> bool:
        """The block creature i carries, set down crosswise just in front of it if the ground there is clear."""
        k = self.block_load[a, i]
        ahead = self.cfg.creature.radius + self.cfg.block[k].w / 2 + 0.05
        h = self.heading[a, i]
        at = self.pos[a, i] + ahead * np.array([np.cos(h), np.sin(h)])
        if self.physics.set_down(a, k, at, h):
            self._wait_to_shut(a, k)
            self.block_load[a, i] = -1
            return True
        return False

    def _wait_to_shut(self, a, k):
        if self.cfg.block[k].shut > 0:
            self.shut_in[a, k] = round(self.cfg.block[k].shut * self.cfg.tick_hz)

    def _swing_shut(self):
        """Blocks that swing shut and have waited their time go back where they started, if nothing's in the way."""
        waiting = self.shut_in > 0
        self.shut_in[waiting] -= 1
        for a, k in zip(*np.nonzero(self.shut_in == 0)):
            b = self.cfg.block[k]
            if self.physics.set_down(a, k, (b.x, b.y), b.angle):
                self.shut_in[a, k] = -1

    def _put_down(self, a, i, spot):
        cfg = self.cfg
        f = self.load[a, i]
        room = cfg.arena.size / 2 - cfg.food.radius
        self.food_pos[a, f] = np.clip(spot, -room, room)
        self.food_regrow[a, f] = 0
        self.food_by[a, f] = i
        self.load[a, i] = -1
        home = np.hypot(*(self.food_pos[a, f] - self.nests[self.colony[i]]))
        self.put_home[a, i] += home < cfg.colonies.nest_radius + cfg.food.radius

    def _credit(self, arena, food, who):
        """A berry someone put down, taken by a nestmate: counted to whoever put it there."""
        by = self.food_by[arena, food]
        given = (by >= 0) & (by != who)
        given[given] &= self.colony[by[given]] == self.colony[who[given]]
        np.add.at(self.given, (arena[given], by[given]), 1)
        hungry = given & (self.energy[arena, who] < self.cfg.jelly.hunger)
        np.add.at(self.given_hungry, (arena[hungry], by[hungry]), 1)
        self.food_by[arena, food] = -1

    def _drink(self):
        """The first to touch an open flower drinks it: its food's worth eaten while hungry, the rest carried while
        there's room in the crop, and a boost of speed."""
        cfg = self.cfg
        reach = cfg.creature.radius + cfg.flowers.radius
        dx = self.pos[:, :, None, 0] - self.flower_pos[:, None, :, 0]
        dy = self.pos[:, :, None, 1] - self.flower_pos[:, None, :, 1]
        touching = (dx * dx + dy * dy < reach * reach) & self.flowers_open[:, None] & self.alive[..., None]
        drunk = touching.any(1)
        if not drunk.any():
            return
        arena, flower = np.nonzero(drunk)
        who = touching.argmax(1)[arena, flower]
        self.flower_left[arena, flower] = 0
        np.add.at(self.drunk, (arena, who), 1)
        self.nectar[arena, who] = round(cfg.flowers.boost * cfg.tick_hz)
        for _ in range(cfg.flowers.food):
            hungry = self.energy[arena, who] <= 1 - cfg.energy.food
            self.energy[arena[hungry], who[hungry]] += cfg.energy.food
            self.fed[arena[hungry], who[hungry]] += cfg.energy.food
            room = ~hungry & (self.crop[arena, who] < cfg.crop.capacity)
            self.crop[arena[room], who[room]] += 1
        log.trace('flowers drunk', tick=self.tick, count=len(arena))

    def _bloom(self):
        """By day, a flower opens once the wait for it is up, if there's room for another; open ones wither."""
        np.maximum(self.flower_left - 1, 0, out=self.flower_left)
        day = ~self.dark
        self.flower_due[day] = np.maximum(self.flower_due[day] - 1, 0)
        free = ~self.flowers_open
        for a in np.flatnonzero(day & (self.flower_due == 0) & free.any(1)):
            f = free[a].argmax()
            self.flower_pos[a, f] = self._flower_spot(a)
            self.flower_left[a, f] = round(self.cfg.flowers.open * self.cfg.tick_hz)
            self.flower_id[a, f] = self.next_id[a]
            self.next_id[a] += 1
            self.flower_due[a] = self._flower_wait(1)[0]

    def _place_spots(self, a):
        fl = self.cfg.flowers
        for k in range(fl.spots):
            for _ in range(PLACE_TRIES):
                p = self._open_ground(a)
                if all(np.hypot(*(p - q)) >= fl.spot_gap for q in self.flower_spots[a, :k]):
                    break
            else:
                raise ValueError(f'no room for {fl.spots} flower spots {fl.spot_gap} m apart')
            self.flower_spots[a, k] = p

    def _flower_spot(self, a) -> np.ndarray:
        """Where the next flower opens: anywhere clear, or one of the arena's spots without an open flower."""
        if not self.cfg.flowers.spots:
            return self._open_ground(a)
        spots = self.flower_spots[a]
        taken = self.flower_pos[a][self.flowers_open[a]]
        free = [k for k in range(len(spots)) if not any(np.allclose(spots[k], t) for t in taken)]
        return spots[free[self.rng.integers(len(free))]] if free else spots[self.rng.integers(len(spots))]

    def _flower_wait(self, count: int) -> np.ndarray:
        fl, hz = self.cfg.flowers, self.cfg.tick_hz
        # drawn only with flowers on, so worlds without them keep their food where it was
        if not fl.on:
            return np.zeros(count, int)
        return self.rng.integers(round(fl.every_min * hz), round(fl.every_max * hz) + 1, count)

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
        young = self.young > 0
        # the young eat from it whenever they aren't full, hungry or not, but a bite their size: everything costs them
        # [young] energy of what it costs a grown one, so a jelly goes that much further, and they take only what fits
        hunger = np.where(young, 1.0, cfg.jelly.hunger)
        wants = eat & (self.crop == 0) & (self.nest_at() == self.colony) & (self.energy < hunger)
        bite = np.where(young, np.minimum(1.0, (1 - self.energy) / cfg.jelly.energy) * cfg.young.energy, 1.0)
        gain = np.where(young, np.minimum(1 - self.energy, cfg.jelly.energy), cfg.jelly.energy)
        for c in range(len(self.nests)):
            # a bite each, lowest index first, while the store lasts; the last one takes what's left (a young one's
            # bites can leave part of a jelly)
            mine = wants & (self.colony == c)
            before = np.cumsum(bite * mine, 1) - bite * mine
            left = self.store[:, c, None] - before
            gets = mine & (left > 1e-9)
            took = np.where(gets, np.minimum(bite, left), 0.0)
            self.store[:, c] -= took.sum(1)
            self.energy[gets] += (gain * took / bite)[gets]
            self.jelly[gets] += took[gets]
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
                slot = empty[lays].argmax(1)
                self.egg[lays, slot] = max(1, round(h.seconds * self.cfg.tick_hz))
                self.store[lays, c] -= h.cost
                # laid where it will hatch, somewhere in the nest
                angle = self.rng.uniform(0, 2 * np.pi, len(lays))
                r = self.cfg.colonies.nest_radius / 2 * np.sqrt(self.rng.uniform(size=len(lays)))
                self.egg_pos[lays, slot] = self.nests[c] + np.stack([np.cos(angle), np.sin(angle)], -1) * r[:, None]
                self.egg_id[lays, slot] = self.next_id[lays]
                self.next_id[lays] += 1

    def _born(self, due: np.ndarray):
        """Hatchlings in these (arenas, creatures) slots, where their eggs were."""
        a, i = np.nonzero(due)
        self.physics.revive(a, i, self.egg_pos[a, i])
        self.heading[a, i] = self.rng.uniform(-np.pi, np.pi, len(a))
        self.energy[a, i] = self.cfg.energy.start
        self.alive[a, i] = True
        self.unborn[a, i] = False
        self.crop[a, i] = 0
        self.sprinting[a, i] = self.resting[a, i] = self.gripping[a, i] = self.nectar[a, i] = 0
        self.stamina[a, i] = 1
        self.young[a, i] = round(self.cfg.young.seconds * self.cfg.tick_hz)
        np.add.at(self.hatched, (a, self.colony[i]), 1)
        self.creature_id[a, i] = self.egg_id[a, i]
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
        # flowers close at nightfall
        self.flower_left[fell] = 0
        standing = (self.food_regrow[:, :self.wild] == 0) & fell[:, None]
        hz = self.cfg.tick_hz
        lo, hi = round(self.cfg.food.regrow_min * hz), round(self.cfg.food.regrow_max * hz)
        self.food_regrow[:, :self.wild][standing] = self.rng.integers(lo, hi + 1, int(standing.sum()))
        self.food_by[:, :self.wild][standing] = -1
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

    def berry_in_reach(self) -> np.ndarray:
        """(arenas, creatures): who could pick up a berry now, carrying nothing."""
        if not self.cfg.carry.on:
            return np.zeros_like(self.alive)
        cfg = self.cfg
        reach = cfg.creature.radius + cfg.food.radius + cfg.carry.reach
        dx = self.pos[:, :, None, 0] - self.food_pos[:, None, :self.wild, 0]
        dy = self.pos[:, :, None, 1] - self.food_pos[:, None, :self.wild, 1]
        near = (dx * dx + dy * dy < reach * reach) & self.food_present[:, None, :self.wild]
        return near.any(-1) & (self.load < 0) & self.alive

    def block_in_reach(self) -> np.ndarray:
        """(arenas, creatures): who could lift a block now, carrying nothing and with no berry in reach."""
        out = np.zeros_like(self.alive)
        if not (self.cfg.carry.on and self.carryable.any()):
            return out
        free = self.alive & (self.load < 0) & (self.block_load < 0) & ~self.berry_in_reach()
        for a, i in zip(*np.nonzero(free)):
            k = self.physics.nearest_block(a, i, self.cfg.carry.reach)
            out[a, i] = k >= 0 and self.carryable[k]
        return out

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
