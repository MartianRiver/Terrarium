# Droppings ([dung], every 0 is off). Every `every` meals, a Terrikin leaves a
# dropping just behind it `after` seconds later. Each lies `lasts` seconds (up to
# `slots` at once in an arena) and makes anyone within `near` of it (from their
# edge) sick, `sick` energy a second, as `away` of that outside every nest.
#
# Carry picks one up as it does a berry, whichever is nearer, and puts it down
# in front. Droppings lying within `pile` of each other make a pile, and a pile
# is only as bad as one dropping: what one Terrikin carries off its own patch
# stops its own sickness, but only piling them all in one place, a midden like
# ants keep, takes the sickness off everyone.
#
# The tidy nursery: `start` droppings lie in each nest at the start, and one put
# down further than `midden` from its carrier's nest edge (having been picked up
# nearer) is worth `points` to the colony. With `start` it then goes, and a new
# one turns up in the nest.
#
# With `spot` the midden is a spot instead of a line all round: `midden` past the nest's edge, `wander` degrees either
# side of due east, anew each episode. One put down on it stays, on a heap that can't be picked up again (so nothing
# scores twice), the oldest on the heap making room when the slots run out; `heap` lie there at the start, to be seen.
import numpy as np


class Droppings:
    def __init__(self, world):
        self.world = world
        d, arenas, n = world.cfg.dung, *world.alive.shape
        self.pos = np.zeros((arenas, d.slots, 2))
        # ticks each has left (0: the slot is empty), and whether someone carries it
        self.left = np.zeros((arenas, d.slots), int)
        self.held = np.zeros((arenas, d.slots), bool)
        self.id = np.zeros((arenas, d.slots), int)
        self.next_id = 1
        # how far from its carrier's nest edge each was when picked up
        self.picked_at = np.zeros((arenas, d.slots))
        # on the midden's heap; and where each arena's midden spot is (with `spot`)
        self.heaped = np.zeros((arenas, d.slots), bool)
        self.midden_at = np.zeros((arenas, 2))
        # per creature: meals since its last, ticks until the next comes out, the one it carries (-1 for none),
        # and since its arena started: made, picked up, taken out past the midden, metres moved further from home
        self.since = np.zeros((arenas, n))
        self.digest = np.zeros((arenas, n), int)
        self.load = np.full((arenas, n), -1)
        self.made = np.zeros((arenas, n), int)
        self.picked = np.zeros((arenas, n), int)
        self.taken = np.zeros((arenas, n), int)
        self.tidied = np.zeros((arenas, n))
        # ticks into the arena's episode of each one's first one taken out, and of its last, and the ticks between
        # each later one and the one before, summed with how many: a midden found once and remembered makes later
        # trips quicker than the first
        self.first_trip = np.zeros((arenas, n), int)
        self.last_trip = np.zeros((arenas, n), int)
        self.later_trips = np.zeros((arenas, n), int)
        self.gain = np.zeros((arenas, len(world.nests)))
        self.reset(np.arange(arenas))

    def reset(self, idx: np.ndarray):
        for arr, v in ((self.left, 0), (self.held, False), (self.heaped, False), (self.since, 0), (self.digest, 0), (self.load, -1),
                       (self.made, 0), (self.picked, 0), (self.taken, 0), (self.tidied, 0), (self.gain, 0),
                       (self.first_trip, 0), (self.last_trip, 0), (self.later_trips, 0)):
            arr[idx] = v
        w, d = self.world, self.world.cfg.dung
        for a in idx:
            if d.spot > 0:
                bearing = np.radians(d.wander) * (2 * w.rng.random() - 1)
                spot = w.nests[0] + (w.cfg.colonies.nest_radius + d.midden) * np.array([np.cos(bearing), np.sin(bearing)])
                # a nest off the middle can point it past a wall: then it's as far out as the arena lets it be
                self.midden_at[a] = np.clip(spot, -(w.cfg.arena.size / 2 - d.spot), w.cfg.arena.size / 2 - d.spot)
                for _ in range(d.heap):
                    r, t = d.spot * 0.5 * np.sqrt(w.rng.random()), w.rng.random() * 2 * np.pi
                    k = self._new(a, self.midden_at[a] + r * np.array([np.cos(t), np.sin(t)]))
                    if k >= 0:
                        self.heaped[a, k] = True
            for c in range(len(w.nests)):
                for _ in range(d.start):
                    self._at_home(a, c)

    def lying(self) -> np.ndarray:
        """(arenas, slots): droppings on the ground."""
        return (self.left > 0) & ~self.held

    def loose(self) -> np.ndarray:
        """(arenas, slots): droppings on the ground that can be picked up (not on the midden's heap)."""
        return self.lying() & ~self.heaped

    def step(self, ate: np.ndarray):
        """ate: meals each creature had this tick. Meals become droppings, droppings go, and lying near them makes
        you sick."""
        w, d = self.world, self.world.cfg.dung
        self.since += ate
        due = (self.since >= d.every) & (self.digest == 0) & (d.every > 0)
        self.since[due] -= d.every
        self.digest[due] = max(round(d.after * w.cfg.tick_hz), 1)
        waiting = self.digest > 0
        self.digest[waiting] -= 1
        for a, i in zip(*np.nonzero(waiting & (self.digest == 0) & w.alive)):
            h = w.heading[a, i]
            behind = -np.array([np.cos(h), np.sin(h)]) * (w.cfg.creature.radius + d.radius)
            if self._new(a, w.pos[a, i] + behind) >= 0:
                self.made[a, i] += 1
        # the tidy nursery's never go by themselves
        if not d.start:
            np.maximum(self.left - 1, 0, out=self.left)
            # one carried till it's gone leaves empty jaws
            gone = self.held & (self.left == 0)
            if gone.any():
                self.held &= ~gone
                k = np.where(self.load >= 0, self.load, 0)
                self.load[np.take_along_axis(gone, k, 1) & (self.load >= 0)] = -1
        w.energy = np.clip(w.energy - d.sick * self.dirt() * w.cfg.dt * w.alive, 0, 1)

    def dirt(self) -> np.ndarray:
        """(arenas, creatures): droppings lying within `near` of each creature's edge, a pile counting as one and
        those outside every nest as `away` of one."""
        w, d = self.world, self.world.cfg.dung
        lying = self.lying()
        gap = self.pos[:, :, None] - w.nests                          # A,D,C,2
        housed = (gap[..., 0] ** 2 + gap[..., 1] ** 2 < w.cfg.colonies.nest_radius ** 2).any(-1)
        weight = lying * np.where(housed, 1.0, d.away)
        if d.pile > 0:
            px = self.pos[:, :, None, 0] - self.pos[:, None, :, 0]
            py = self.pos[:, :, None, 1] - self.pos[:, None, :, 1]
            together = ((px * px + py * py < d.pile ** 2) & lying[:, None]).sum(-1)
            weight = weight / np.maximum(together, 1)
        dx = w.pos[:, :, None, 0] - self.pos[:, None, :, 0]
        dy = w.pos[:, :, None, 1] - self.pos[:, None, :, 1]
        r = w.cfg.creature.radius + d.near
        return ((dx * dx + dy * dy < r * r) * weight[:, None]).sum(-1)

    def nearest(self, a: int, i: int) -> tuple[int, float]:
        """The dropping lying nearest creature i, and the gap between their edges (inf if none)."""
        w = self.world
        gap = np.where(self.loose()[a], np.hypot(*(self.pos[a] - w.pos[a, i]).T), np.inf) - w.cfg.dung.radius
        k = int(gap.argmin()) if len(gap) else -1
        return k, (gap[k] - w.cfg.creature.radius if k >= 0 else np.inf)

    def in_reach(self) -> np.ndarray:
        """(arenas, creatures): who could pick up a dropping now, carrying nothing."""
        w = self.world
        if not w.cfg.carry.on:
            return np.zeros_like(w.alive)
        dx = w.pos[:, :, None, 0] - self.pos[:, None, :, 0]
        dy = w.pos[:, :, None, 1] - self.pos[:, None, :, 1]
        r = w.cfg.creature.radius + w.cfg.dung.radius + w.cfg.carry.reach
        near = ((dx * dx + dy * dy < r * r) & self.loose()[:, None]).any(-1)
        return near & (w.load < 0) & (w.block_load < 0) & (self.load < 0) & w.alive

    def pick(self, a: int, i: int, k: int):
        self.held[a, k] = True
        self.load[a, i] = k
        self.picked[a, i] += 1
        self.picked_at[a, k] = self._from_home(i, self.pos[a, k])

    def put(self, a: int, i: int, spot):
        """Creature i puts down what it carries at spot."""
        w, d = self.world, self.world.cfg.dung
        k = self.load[a, i]
        room = w.cfg.arena.size / 2 - d.radius
        self.pos[a, k] = np.clip(spot, -room, room)
        self.held[a, k] = False
        self.load[a, i] = -1
        out = self._from_home(i, self.pos[a, k])
        self.tidied[a, i] += out - self.picked_at[a, k]
        if d.spot > 0:
            scored = np.hypot(*(self.pos[a, k] - self.midden_at[a])) < d.spot
        else:
            scored = d.midden > 0 and out > d.midden >= self.picked_at[a, k]
        if scored:
            self.taken[a, i] += 1
            now = int(w.age[a])
            if self.taken[a, i] == 1:
                self.first_trip[a, i] = now
            else:
                self.later_trips[a, i] += now - self.last_trip[a, i]
            self.last_trip[a, i] = now
            self.gain[a, w.colony[i]] += d.points
            if d.spot > 0:
                self.heaped[a, k] = True
            elif d.start:
                self.left[a, k] = 0
            if d.start:
                self._at_home(a, w.colony[i])

    def born(self, a, i):
        self.since[a, i] = self.digest[a, i] = 0

    def died(self, dying: np.ndarray):
        for a, i in zip(*np.nonzero(dying & (self.load >= 0))):
            self.put(a, i, self.world.pos[a, i])
        self.since[dying] = self.digest[dying] = 0

    def points(self, alive: np.ndarray) -> np.ndarray:
        """What each creature's colony earned since last asked, (arenas, creatures)."""
        out, self.gain = self.gain[:, self.world.colony] * alive, np.zeros(self.gain.shape)
        return out

    def _from_home(self, i, p) -> float:
        w = self.world
        return float(np.hypot(*(p - w.nests[w.colony[i]]))) - w.cfg.colonies.nest_radius

    def _new(self, a, spot) -> int:
        """Puts a dropping at spot and gives its slot, or -1 when there's no room."""
        w, d = self.world, self.world.cfg.dung
        free = np.flatnonzero(self.left[a] == 0)
        if not len(free):
            # the heap's oldest sinks in to make room
            heap = np.flatnonzero(self.heaped[a])
            if not len(heap):
                return -1
            free = [heap[self.id[a, heap].argmin()]]
        k = free[0]
        self.heaped[a, k] = False
        room = w.cfg.arena.size / 2 - d.radius
        self.pos[a, k] = np.clip(spot, -room, room)
        self.left[a, k] = max(round(d.lasts * w.cfg.tick_hz), 1)
        self.held[a, k] = False
        self.id[a, k] = self.next_id
        self.next_id += 1
        return int(k)

    def _at_home(self, a, c):
        """A dropping somewhere in nest c."""
        w = self.world
        r = w.cfg.colonies.nest_radius * np.sqrt(w.rng.random())
        t = w.rng.random() * 2 * np.pi
        self._new(a, w.nests[c] + r * np.array([np.cos(t), np.sin(t)]))
