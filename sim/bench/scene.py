# The scene both physics candidates run: the stage 0 demo's arena, in sim terms.
# Sizes and speeds match viewer/src/demo.ts.

import numpy as np

DT = 1 / 20
MAP = 26.0
HALF = MAP / 2

CREATURES = 18
RADIUS = 0.45
CREATURE_MASS = 1.0
MAX_SPEED = 2.4
TURN_RATE = 3.5
# how fast velocity catches up with what the creature asks for, per second
ACCEL = 8.0

FOOD = 30
FOOD_RADIUS = 0.25

# (w, h, mass): a light cube and a heavy slab
BLOCKS = [(1.3, 1.3, 4.0), (2.4, 1.1, 12.0)]
BLOCK_START = [(3.5, 3.0), (-4.0, -3.5)]
# how fast a sliding block slows on the ground, m/s² (friction coefficient times g)
GROUND_FRICTION = 1.2

RAYS = 16
RAY_FOV = np.radians(200)
RAY_RANGE = 8.0


def friction_torque(w, h, m):
    # average lever arm of the ground under a spinning box, roughly a third of its diagonal
    return m * GROUND_FRICTION * np.hypot(w, h) / 3


def initial_state(arenas: int, seed: int):
    rng = np.random.default_rng(seed)
    pos = np.empty((arenas, CREATURES, 2))
    # creatures start in a loose grid with jitter, so nothing overlaps at tick 0
    grid = np.stack(np.meshgrid(np.linspace(-9, 9, 6), np.linspace(-6, 9, 3)), -1).reshape(-1, 2)
    pos[:] = grid + rng.uniform(-0.4, 0.4, (arenas, CREATURES, 2))
    heading = rng.uniform(-np.pi, np.pi, (arenas, CREATURES))
    return pos, heading


class Food:
    """Eaten on touch, regrows somewhere random after a few seconds. Game logic, not physics, so both candidates share it."""

    def __init__(self, arenas: int, seed: int):
        self.rng = np.random.default_rng(seed + 2)
        self.pos = self.rng.uniform(-HALF + 1.5, HALF - 1.5, (arenas, FOOD, 2))
        self.regrow = np.zeros((arenas, FOOD), int)
        self.eaten = 0

    @property
    def alive(self):
        return self.regrow == 0

    def update(self, creatures: np.ndarray):
        d = creatures[:, :, None] - self.pos[:, None]
        touched = ((d * d).sum(-1) < (RADIUS + FOOD_RADIUS) ** 2).any(1) & self.alive
        self.eaten += int(touched.sum())
        self.regrow = np.maximum(self.regrow - 1, 0)
        self.regrow[touched] = self.rng.integers(120, 240, int(touched.sum()))
        self.pos[touched] = self.rng.uniform(-HALF + 1.5, HALF - 1.5, (int(touched.sum()), 2))
        return touched


class RandomActions:
    """Each creature holds a random (thrust, turn) for a random spell, then picks again."""

    def __init__(self, arenas: int, seed: int):
        self.rng = np.random.default_rng(seed + 1)
        self.current = self._draw((arenas, CREATURES))

    def _draw(self, shape):
        thrust = self.rng.uniform(-0.3, 1.0, shape)
        turn = self.rng.uniform(-1.0, 1.0, shape)
        return np.stack([thrust, turn], -1)

    def __call__(self) -> np.ndarray:
        shape = self.current.shape[:2]
        switch = self.rng.random(shape) < 0.05
        self.current = np.where(switch[..., None], self._draw(shape), self.current)
        return self.current


def steer(heading, vel, actions):
    """Shared creature motion: turn, then ease velocity toward thrust along the new heading."""
    heading = heading + actions[..., 1] * TURN_RATE * DT
    heading = (heading + np.pi) % (2 * np.pi) - np.pi
    forward = np.stack([np.cos(heading), np.sin(heading)], -1)
    target = forward * (actions[..., :1] * MAX_SPEED)
    vel = vel + (target - vel) * min(1.0, ACCEL * DT)
    return heading, vel
