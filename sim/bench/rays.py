# Ray vision in numpy, for every creature in every arena at once. Works off
# plain position arrays, so it can sit on top of either physics candidate.

import numpy as np

from scene import CREATURES, FOOD_RADIUS, HALF, RADIUS, RAY_FOV, RAY_RANGE, RAYS

NOTHING, WALL, CREATURE, FOOD, BLOCK = range(5)
# rays start just outside the body; anything already overlapping that point is hit at START
START = RADIUS + 0.01
SPREAD = np.linspace(-RAY_FOV / 2, RAY_FOV / 2, RAYS)


def directions(heading):
    a = heading[..., None] + SPREAD
    return np.stack([np.cos(a), np.sin(a)], -1)


def hit_circles(origin, dirs, centres, radius, valid):
    """Nearest hit along each ray against circles. origin (A,N,2), dirs (A,N,R,2), centres (A,M,2), valid (A,N,M)."""
    oc = centres[:, None] - origin[:, :, None]                      # A,N,M,2
    along = np.einsum('anrk,anmk->anrm', dirs, oc)
    miss2 = (oc * oc).sum(-1)[:, :, None] - along * along
    inside = radius * radius - miss2
    root = np.sqrt(np.maximum(inside, 0))
    ok = (inside > 0) & (along + root > START) & valid[:, :, None]
    return np.where(ok, np.maximum(along - root, START), np.inf).min(-1)


def hit_boxes(origin, dirs, bpos, bang, half):
    """Slab test in each box's own frame. Returns the nearest entry distance per ray."""
    cos, sin = np.cos(bang), np.sin(bang)                            # A,B
    rel = origin[:, :, None] - bpos[:, None]                         # A,N,B,2
    c, s = cos[:, None], sin[:, None]
    ox = (c * rel[..., 0] + s * rel[..., 1])[:, :, None]             # A,N,1,B
    oy = (-s * rel[..., 0] + c * rel[..., 1])[:, :, None]
    c, s = c[:, None], s[:, None]
    dx = c * dirs[..., 0, None] + s * dirs[..., 1, None]             # A,N,R,B
    dy = -s * dirs[..., 0, None] + c * dirs[..., 1, None]
    with np.errstate(divide='ignore', invalid='ignore'):
        tx1, tx2 = (-half[:, 0] - ox) / dx, (half[:, 0] - ox) / dx
        ty1, ty2 = (-half[:, 1] - oy) / dy, (half[:, 1] - oy) / dy
    near = np.maximum(np.minimum(tx1, tx2), np.minimum(ty1, ty2))
    far = np.minimum(np.maximum(tx1, tx2), np.maximum(ty1, ty2))
    ok = (near <= far) & (far > START)
    return np.where(ok, np.maximum(near, START), np.inf).min(-1)


def hit_walls(origin, dirs):
    with np.errstate(divide='ignore', invalid='ignore'):
        t = (np.sign(dirs) * HALF - origin[:, :, None]) / dirs
    return np.where(t > START, t, np.inf).min(-1)


def cast(pos, heading, food_pos, food_alive, bpos, bang, half):
    """Distance and kind of the first thing each ray meets, out to RAY_RANGE."""
    dirs = directions(heading)
    arenas = pos.shape[0]
    others = np.broadcast_to(~np.eye(CREATURES, dtype=bool), (arenas, CREATURES, CREATURES))
    fed = np.broadcast_to(food_alive[:, None], (arenas, CREATURES, food_alive.shape[1]))
    hits = np.stack([
        np.minimum(hit_walls(pos, dirs), RAY_RANGE),
        hit_circles(pos, dirs, pos, RADIUS, others),
        hit_circles(pos, dirs, food_pos, FOOD_RADIUS, fed),
        hit_boxes(pos, dirs, bpos, bang, half),
    ], -1)
    kind = hits.argmin(-1) + WALL
    dist = hits.min(-1)
    kind[dist >= RAY_RANGE] = NOTHING
    return np.minimum(dist, RAY_RANGE), kind
