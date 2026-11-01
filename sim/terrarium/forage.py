# The world as training sees it: every creature in every arena is one sample,
# observed as a self token plus a token per ray (terrarium.schema), rewarded
# for the energy it gets from food and for food it stores, charged for eating
# the store's jelly and for the energy it spends moving, paid when its colony
# hatches a new member, and punished for dying (configs/train.toml), with part
# of each reward shared out over its colony. Carrying food home is paid on the
# way (potential-based shaping, Ng, Harada & Russell 1999): what's in the crop
# is worth more the nearer home it is, and the reward is the change in that
# worth, so it moves the store's pay earlier without changing which way of
# living pays best. Arenas that end are started over straight away, so a step
# always hands back a full batch; a creature that has died is still in it,
# marked inactive, until its arena starts over or a hatchling takes its place.
#
# Running out of time is an end like any other unless [ppo] bootstrap is on: then a
# creature cut off alive is marked in `cut` and its last look kept in `final`, so the
# learner can carry on its value instead of teaching it that time running out is death.
#
# `hint` is a label per sample for a side job, never seen by the brain: in a maze, whether
# the creature has been in this room before (maze.Visits); 0 in other worlds.

from dataclasses import dataclass

import numpy as np

from . import hearing, maze, night, vision
from .fun import Fun
from .config import Config, Reward, Train
from .vision import directions, look
from .world import World


@dataclass
class Observation:
    me: np.ndarray      # (samples, len(SELF)) float32
    kinds: np.ndarray   # (samples, rays) int64
    rays: np.ndarray    # (samples, rays, len(RAY)) float32


def observe(world: World, last: np.ndarray) -> Observation:
    """last is each creature's previous thrust and turn, (arenas, creatures, 2)."""
    cfg, v = world.cfg, world.cfg.vision
    sight = look(world)
    facing = directions(world.heading, np.zeros(1))[..., 0, :]      # A,N,2
    vel = world.vel / cfg.creature.max_speed
    forward = (vel * facing).sum(-1)
    side = facing[..., 0] * vel[..., 1] - facing[..., 1] * vel[..., 0]
    # the way home, as an ant keeps track of it: how far, and which way off the heading
    home = world.nests[world.colony] - world.pos
    # how much jelly its colony has, as an ant knows how hungry its nest is: near 1 at a jelly a member
    store = np.tanh(np.take_along_axis(world.store, np.broadcast_to(world.colony, world.crop.shape), 1) / cfg.colonies.size)
    bearing = np.arctan2(home[..., 1], home[..., 0]) - world.heading
    # how much of its sprint is left, how far through its rest it is (1: it can sprint now; 0 with sprint off),
    # holding a block, how much of its grip is left, how much of a nectar boost, and a berry (or block) in its jaws
    s = cfg.sprint
    sprinting = world.sprinting / max(round(s.seconds * cfg.tick_hz), 1)
    rested = (1 - world.resting / max(round(s.cooldown * cfg.tick_hz), 1)) * (world.sprinting == 0) * s.on
    me = np.stack([world.energy, forward, side, last[..., 0], last[..., 1],
                   np.hypot(home[..., 0], home[..., 1]) / v.range, np.sin(bearing), np.cos(bearing),
                   world.crop / max(cfg.crop.capacity, 1), world.nest_at() == world.colony, store,
                   np.broadcast_to(world.light()[:, None], store.shape), sprinting, rested,
                   world.holding * world.gripping / max(round(cfg.grab.seconds * cfg.tick_hz), 1),
                   *world.smelled(), world.nectar / max(round(cfg.flowers.boost * cfg.tick_hz), 1),
                   (world.load >= 0) | (world.block_load >= 0), world.young / max(round(cfg.young.seconds * cfg.tick_hz), 1),
                   world.tag.mask() if world.tag else np.zeros(store.shape),
                   *((np.broadcast_to(world.seek.seeker, store.shape), np.broadcast_to(world.seek.waiting()[:, None], store.shape))
                     if world.seek else (np.zeros(store.shape),) * 2),
                   *flag_senses(world, store.shape), world.stamina, *hearing.heard(world),
                   *dung_senses(world, store.shape)], -1)

    angles = vision.angles(v)
    shape = sight.dist.shape
    rays = np.stack([sight.dist / v.range, *(np.broadcast_to(f(angles), shape) for f in (np.sin, np.cos)),
                     sight.nestmate, sight.own_nest / v.range, sight.other_nest / v.range, sight.it, sight.carrier], -1)
    return Observation(me.reshape(-1, me.shape[-1]).astype(np.float32),
                       sight.kind.reshape(-1, v.rays).astype(np.int64),
                       rays.reshape(-1, v.rays, rays.shape[-1]).astype(np.float32))


class Forage:
    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int):
        self.world = World(cfg, arenas, seed)
        self.staggered = train.start.staggered and cfg.night.on
        self._stagger(np.ones(arenas, bool))
        if train.start.spread:
            self.world.age[:] = self.world.rng.integers(0, self.world.episode_ticks, arenas)
        self.reward = train.reward
        r = self.reward
        self.fun = Fun(self.world, r.novelty, r.variety) if r.novelty or r.variety else None
        self.repeat = train.ppo.repeat
        if self.world.episode_ticks % self.repeat:
            raise ValueError(f'{self.world.episode_ticks} ticks an episode is not a whole number of {self.repeat}-tick choices')
        # the shaping has to be discounted the way PPO discounts, or it isn't neutral
        self.gamma = train.ppo.gamma
        self.last = np.zeros((arenas, len(self.world.colony), 2))
        self.bootstrap = train.ppo.bootstrap
        # after a step where arenas ran out of time: which samples were cut off alive, and where they got to
        self.cut = np.zeros(self.samples, bool)
        self.final: Observation | None = None
        self.visits = maze.Visits(self.world) if cfg.arena.maze else None
        self.hint = np.zeros(self.samples, np.float32)

    @property
    def samples(self) -> int:
        return self.last.shape[0] * self.last.shape[1]

    def observe(self) -> Observation:
        return observe(self.world, self.last)

    @property
    def active(self) -> np.ndarray:
        """Which samples are alive and acting, (samples,)."""
        return self.world.alive.reshape(-1).copy()

    def step(self, actions: np.ndarray) -> tuple[Observation, np.ndarray, np.ndarray, np.ndarray]:
        """actions (samples, len(ACTIONS)) → next observation, reward and done per sample, and which arenas ended.
        A sample is done when its creature dies or its arena ends."""
        w, r = self.world, self.reward
        actions = np.clip(actions, -1, 1).reshape(*self.last.shape[:2], -1)
        before = {k: getattr(w, k).copy() for k in ('fed', 'spent', 'stored', 'jelly', 'hatched', 'alive')}
        alive = before['alive']
        worth = carried_worth(w, r)
        # held for `repeat` ticks; episodes are a whole number of choices long, so a time limit lands on the last
        # tick, and an arena where everyone has died only ticks on with nobody in it
        lived, snug, fun, play = (np.zeros(alive.shape) for _ in range(4))
        for _ in range(self.repeat):
            w.step(actions)
            lived += w.alive
            if w.tag:
                play += w.tag.points(w.alive)
            if w.seek:
                play += w.seek.points(w.alive)
            if w.flags:
                play += w.flags.points(w.alive)
            if w.peek:
                play += w.peek.points(w.alive)
            if w.dung:
                play += w.dung.points(w.alive)
            if self.fun:
                fun += self.fun.step(actions)
            if r.snug or r.warm:
                warm = night.warmth(w.pos, w.alive, w.colony, w.nest_at() == w.colony, w.cfg.night)
                snug += w.alive * warm * (r.snug + r.warm * (1 - w.light())[:, None])
        self.last = actions[..., :2].copy()
        own = ((r.food * (w.fed - before['fed']) - r.effort * (w.spent - before['spent'])) / w.cfg.energy.food
               + r.stored * (w.stored - before['stored']) + r.jelly * (w.jelly - before['jelly'])
               + r.hatch * (w.hatched - before['hatched'])[:, w.colony] * alive + r.death * (alive & ~w.alive)
               + w.cfg.dt * (r.alive * lived + snug) + fun + play)
        ended = w.ended.copy()
        died = alive & ~w.alive
        done = died | ended[:, None]
        cut = ended[:, None] & w.alive & self.bootstrap
        own += self.gamma * np.where(done & ~cut, 0, carried_worth(w, r)) - worth
        reward = (1 - r.colony) * own + r.colony * colony_mean(own, alive, w.colony)
        self.cut = cut.reshape(-1)
        self.final = self.observe() if cut.any() else None
        w.reset(ended)
        self._stagger(ended)
        if self.fun:
            self.fun.reset(ended)
        self.last[ended] = 0
        if self.visits:
            self.visits.reset(ended)
            self.hint = self.visits.update()
        return self.observe(), reward.reshape(-1).astype(np.float32), done.reshape(-1).copy(), ended

    def _stagger(self, arenas: np.ndarray):
        # a start in the dark loses its standing food on the first step, as at nightfall
        if self.staggered:
            self.world.clock[arenas] = self.world.rng.uniform(0, self.world.cfg.night.cycle, int(arenas.sum()))



def flag_senses(world: World, shape) -> tuple:
    """Carrying their flag, the way to it (how far, which way off the heading), whether ours is off its nest, then
    carrying ours and the way to it."""
    if not world.flags:
        return (np.zeros(shape),) * 9
    flags = world.flags
    where, held = flags.where(), flags.held()
    out = []
    for side in (1 - world.colony, world.colony):
        to = where[:, side] - world.pos                              # A,N,2
        bearing = np.arctan2(to[..., 1], to[..., 0]) - world.heading
        out.append((held == side, np.hypot(to[..., 0], to[..., 1]) / world.cfg.vision.range, np.sin(bearing), np.cos(bearing)))
    taken = ((flags.carrier >= 0) | flags.down)[:, world.colony]
    return (*out[0], taken, *out[1])

def carried_worth(world: World, r: Reward) -> np.ndarray:
    """What the food in each crop is worth where it is: r.home a food at its own nest, falling to nothing an arena's width away."""
    home = world.nests[world.colony] - world.pos
    near = np.clip(1 - np.hypot(home[..., 0], home[..., 1]) / world.cfg.arena.size, 0, 1)
    return r.home * world.crop * near


def colony_mean(x: np.ndarray, alive: np.ndarray, colony: np.ndarray) -> np.ndarray:
    """Each creature's colony's average of x over those that were alive, (arenas, creatures)."""
    out = np.zeros_like(x, dtype=float)
    for c in np.unique(colony):
        mine = colony == c
        live = alive[:, mine]
        mean = (x[:, mine] * live).sum(1) / np.maximum(live.sum(1), 1)
        out[:, mine] = mean[:, None]
    return out


def dung_senses(world: World, shape) -> tuple:
    """How many droppings lie close (a pile as one; 1 at four or more), and carrying one."""
    if not world.dung:
        return (np.zeros(shape),) * 2
    return np.minimum(world.dung.dirt() / 4, 1), world.dung.load >= 0
