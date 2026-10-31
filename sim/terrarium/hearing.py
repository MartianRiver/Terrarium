# Hearing ([hearing], range 0 is off): the nearest other Terrikin within range, all the way round. Sight covers
# only what's in front, so in tag a runner could sit just behind whoever's it, out of its view, and circle with it
# for as long as it liked; footsteps that close are heard.
import numpy as np


def heard(world) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """How close the nearest other Terrikin is (1 touching, 0 at `range` metres apart or none), and the sin and cos
    of which way it is off the heading (0 when none), each (arenas, creatures)."""
    h = world.cfg.hearing
    shape = world.energy.shape
    if not h.on:
        return np.zeros(shape), np.zeros(shape), np.zeros(shape)
    d = world.pos[:, None, :, :] - world.pos[:, :, None, :]             # A, me, them, 2
    gap = np.hypot(d[..., 0], d[..., 1]) - 2 * world.cfg.creature.radius
    n = shape[1]
    gap = np.where(world.alive[:, None, :] & ~np.eye(n, dtype=bool), gap, np.inf)
    j = gap.argmin(2)
    near = np.take_along_axis(gap, j[..., None], 2)[..., 0]
    loud = np.clip(1 - np.maximum(near, 0) / h.range, 0, 1) * world.alive
    to = np.take_along_axis(d, j[..., None, None].repeat(2, -1), 2)[:, :, 0]
    bearing = np.arctan2(to[..., 1], to[..., 0]) - world.heading
    some = loud > 0
    return loud, np.sin(bearing) * some, np.cos(bearing) * some
