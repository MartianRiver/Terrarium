# Day and night ([night] in the world config): the light from how long an arena has been going, and how
# much of the night's cold a creature is kept from. An arena starts at dawn unless its clock says otherwise
# (staggered training starts), and a day ends in its night.

import numpy as np

from .config import Night


def light(seconds: np.ndarray, n: Night) -> np.ndarray:
    """1 by day and 0 at night, fading over n.dusk before nightfall and after dawn; always 1 with nights off."""
    if not n.on:
        return np.ones(np.shape(seconds))
    t = np.asarray(seconds) % n.cycle
    day = n.cycle - n.length
    if n.dusk <= 0:
        return (t < day).astype(float)
    return np.clip(np.minimum(t, day - t) / n.dusk, 0, 1)


def dark(seconds: np.ndarray, n: Night) -> np.ndarray:
    """Whether it's night: no food grows, and what was standing at nightfall is gone."""
    if not n.on:
        return np.zeros(np.shape(seconds), bool)
    return np.asarray(seconds) % n.cycle >= n.cycle - n.length


def warmth(pos: np.ndarray, alive: np.ndarray, colony: np.ndarray, home: np.ndarray, n: Night) -> np.ndarray:
    """Share of the cold kept off, (arenas, creatures): by being in its own nest, or by living nestmates close by."""
    dx = pos[:, :, None, 0] - pos[:, None, :, 0]
    dy = pos[:, :, None, 1] - pos[:, None, :, 1]
    mates = (colony[:, None] == colony[None]) & ~np.eye(len(colony), dtype=bool)
    close = (dx * dx + dy * dy < n.reach * n.reach) & mates & alive[:, None, :]
    return np.minimum(1.0, n.nest * home + n.huddle * close.sum(-1))
