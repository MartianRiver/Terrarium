# The world as training sees it: every creature in every arena is one sample,
# observed as a self token plus a token per ray (terrarium.schema), rewarded
# for eating and punished for dying (configs/train.toml). Arenas that end are
# started over straight away, so a step always hands back a full batch.
#
# Running out of time is treated like any other end. With episodes of minutes
# and a discount horizon of seconds, not bootstrapping the cut-off costs nothing.

from dataclasses import dataclass

import numpy as np

from .config import Config, Reward
from .vision import directions, look
from .world import World


@dataclass
class Observation:
    me: np.ndarray      # (samples, len(SELF)) float32
    kinds: np.ndarray   # (samples, rays) int64
    rays: np.ndarray    # (samples, rays, len(RAY)) float32


def observe(world: World, last: np.ndarray) -> Observation:
    """last is each creature's previous action, (arenas, creatures, 2)."""
    cfg, v = world.cfg, world.cfg.vision
    dist, kind = look(world)
    facing = directions(world.heading, 1, 0.0)[..., 0, :]          # A,N,2
    vel = world.vel / cfg.creature.max_speed
    forward = (vel * facing).sum(-1)
    side = facing[..., 0] * vel[..., 1] - facing[..., 1] * vel[..., 0]
    me = np.stack([world.energy, forward, side, last[..., 0], last[..., 1]], -1)

    angles = np.linspace(-v.fov / 2, v.fov / 2, v.rays)
    rays = np.stack([dist / v.range, *(np.broadcast_to(f(angles), dist.shape) for f in (np.sin, np.cos))], -1)
    return Observation(me.reshape(-1, me.shape[-1]).astype(np.float32),
                       kind.reshape(-1, v.rays).astype(np.int64),
                       rays.reshape(-1, v.rays, rays.shape[-1]).astype(np.float32))


class Forage:
    def __init__(self, cfg: Config, reward: Reward, arenas: int, seed: int):
        self.world = World(cfg, arenas, seed)
        self.reward = reward
        self.last = np.zeros((arenas, len(self.world.colony), 2))

    @property
    def samples(self) -> int:
        return self.last.shape[0] * self.last.shape[1]

    def observe(self) -> Observation:
        return observe(self.world, self.last)

    def step(self, actions: np.ndarray) -> tuple[Observation, np.ndarray, np.ndarray, np.ndarray]:
        """actions (samples, 2) → next observation, reward and done per sample, and which arenas ended."""
        w, r = self.world, self.reward
        actions = np.clip(actions, -1, 1).reshape(self.last.shape)
        meals, alive = w.meals.copy(), w.alive.copy()
        w.step(actions)
        self.last = actions
        reward = (r.food * (w.meals - meals) + r.death * (alive & ~w.alive)
                  + r.alive * w.cfg.dt * w.alive)
        ended = w.ended.copy()
        done = np.broadcast_to(ended[:, None], alive.shape)
        w.reset(ended)
        self.last[ended] = 0
        return self.observe(), reward.reshape(-1).astype(np.float32), done.reshape(-1).copy(), ended
