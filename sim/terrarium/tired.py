# [tired]: babies in the nurseries can't starve, so moving cost them nothing and wandering about was as good as waiting
# where something will turn up. With this, each one has stamina (0–1) that goes with how hard it moves (a sprint by
# its speed up) and comes back while it keeps still. Below `below` its top speed sinks, down to `slowest` of it with
# none left: it can still get about, slowly, and resting brings it back. Nobody dies of it. Off with drain 0, and
# stamina stays 1.
import numpy as np


def speed(world) -> np.ndarray | float:
    """The share of top speed tiredness leaves each creature."""
    t = world.cfg.tired
    if not t.on:
        return 1.0
    return np.where(world.stamina < t.below, t.slowest + (1 - t.slowest) * world.stamina / max(t.below, 1e-9), 1.0)


def tire(world, thrust: np.ndarray, bursting: np.ndarray):
    t, dt = world.cfg.tired, world.cfg.dt
    go = np.abs(thrust) * np.where(bursting, world.cfg.sprint.speed, 1.0)
    still = np.abs(thrust) < t.still
    world.stamina = np.where(world.alive, np.clip(world.stamina - t.drain * go * dt + t.rest * still * dt, 0, 1), 1.0)
