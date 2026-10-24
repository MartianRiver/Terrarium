# The world as training sees it: every creature in every arena is one sample,
# observed as a self token plus a token per ray (terrarium.schema), rewarded
# for the energy it gets from food and for food it stores, charged for eating
# the store's jelly and punished for dying (configs/train.toml), with part of
# each reward shared out over its colony. Carrying food home is paid on the way
# (potential-based shaping, Ng, Harada & Russell 1999): what's in the crop is
# worth more the nearer home it is, and the reward is the change in that worth,
# so it moves the store's pay earlier without changing which way of living
# pays best. Arenas that end are started over straight away, so a step always
# hands back a full batch; a creature that has died is still in it, marked
# inactive, until its arena starts over.
#
# Running out of time is treated like any other end. With episodes of minutes
# and a discount horizon of seconds, not bootstrapping the cut-off costs nothing.

from dataclasses import dataclass

import numpy as np

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
    facing = directions(world.heading, 1, 0.0)[..., 0, :]          # A,N,2
    vel = world.vel / cfg.creature.max_speed
    forward = (vel * facing).sum(-1)
    side = facing[..., 0] * vel[..., 1] - facing[..., 1] * vel[..., 0]
    # the way home, as an ant keeps track of it: how far, and which way off the heading
    home = world.nests[world.colony] - world.pos
    bearing = np.arctan2(home[..., 1], home[..., 0]) - world.heading
    me = np.stack([world.energy, forward, side, last[..., 0], last[..., 1],
                   np.hypot(home[..., 0], home[..., 1]) / v.range, np.sin(bearing), np.cos(bearing),
                   world.crop / max(cfg.crop.capacity, 1), world.nest_at() == world.colony], -1)

    angles = np.linspace(-v.fov / 2, v.fov / 2, v.rays)
    shape = sight.dist.shape
    rays = np.stack([sight.dist / v.range, *(np.broadcast_to(f(angles), shape) for f in (np.sin, np.cos)),
                     sight.nestmate, sight.own_nest / v.range, sight.other_nest / v.range], -1)
    return Observation(me.reshape(-1, me.shape[-1]).astype(np.float32),
                       sight.kind.reshape(-1, v.rays).astype(np.int64),
                       rays.reshape(-1, v.rays, rays.shape[-1]).astype(np.float32))


class Forage:
    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int):
        self.world = World(cfg, arenas, seed)
        self.reward = train.reward
        # the shaping has to be discounted the way PPO discounts, or it isn't neutral
        self.gamma = train.ppo.gamma
        self.last = np.zeros((arenas, len(self.world.colony), 2))

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
        before = {k: getattr(w, k).copy() for k in ('fed', 'stored', 'jelly', 'alive')}
        alive = before['alive']
        worth = carried_worth(w, r)
        w.step(actions)
        self.last = actions[..., :2].copy()
        own = (r.food * (w.fed - before['fed']) / w.cfg.energy.food + r.stored * (w.stored - before['stored'])
               + r.jelly * (w.jelly - before['jelly']) + r.death * (alive & ~w.alive) + r.alive * w.cfg.dt * w.alive)
        ended = w.ended.copy()
        done = (alive & ~w.alive) | ended[:, None]
        own += self.gamma * np.where(done, 0, carried_worth(w, r)) - worth
        reward = (1 - r.colony) * own + r.colony * colony_mean(own, alive, w.colony)
        w.reset(ended)
        self.last[ended] = 0
        return self.observe(), reward.reshape(-1).astype(np.float32), done.reshape(-1).copy(), ended


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
