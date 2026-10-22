# Ray vision: a fan of rays from every creature in every arena at once, each
# giving how far it went and the kind of thing it hit first. Plain numpy on the
# positions physics reports. Rays start just outside the body, and anything
# already covering that point counts as hit there, as pymunk's queries do.

import numpy as np

from .world import World

NOTHING, WALL, CREATURE, FOOD, BLOCK = range(5)
# rays start this far outside the body, so a creature never sees itself
GAP = 0.01


def directions(heading, rays, fov):
    a = heading[..., None] + np.linspace(-fov / 2, fov / 2, rays)
    return np.stack([np.cos(a), np.sin(a)], -1)


def look(world: World) -> tuple[np.ndarray, np.ndarray]:
    """How far each ray got from the creature's centre (metres, at most the range) and the kind of thing it hit.
    Both are (arenas, creatures, rays)."""
    cfg, v = world.cfg, world.cfg.vision
    start = cfg.creature.radius + GAP
    pos = world.pos
    arenas, n = pos.shape[:2]
    dirs = directions(world.heading, v.rays, v.fov)
    others = np.broadcast_to(~np.eye(n, dtype=bool), (arenas, n, n))
    food = np.broadcast_to(world.food_present[:, None], (arenas, n, cfg.food.count))
    half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2)
    hits = np.stack([
        hit_walls(pos, dirs, cfg.arena.size / 2, start),
        hit_circles(pos, dirs, pos, cfg.creature.radius, others, start),
        hit_circles(pos, dirs, world.food_pos, cfg.food.radius, food, start),
        hit_boxes(pos, dirs, world.block_pos, world.block_angle, half, start),
    ], -1)
    dist = hits.min(-1)
    seen = dist < v.range
    return np.where(seen, dist, v.range), np.where(seen, hits.argmin(-1) + WALL, NOTHING)


def hit_circles(origin, dirs, centres, radius, valid, start):
    """origin (A,N,2), dirs (A,N,R,2), centres (A,M,2), valid (A,N,M): nearest hit per ray, inf for none."""
    oc = centres[:, None] - origin[:, :, None]                      # A,N,M,2
    along = np.einsum('anrk,anmk->anrm', dirs, oc)
    miss2 = (oc * oc).sum(-1)[:, :, None] - along * along
    inside = radius * radius - miss2
    root = np.sqrt(np.maximum(inside, 0))
    ok = (inside > 0) & (along + root > start) & valid[:, :, None]
    return np.where(ok, np.maximum(along - root, start), np.inf).min(-1, initial=np.inf)


def hit_boxes(origin, dirs, bpos, bang, half, start):
    """Slab test in each box's own frame. bpos (A,B,2), bang (A,B), half (B,2)."""
    c, s = np.cos(bang)[:, None], np.sin(bang)[:, None]             # A,1,B
    rel = origin[:, :, None] - bpos[:, None]                         # A,N,B,2
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
    ok = (near <= far) & (far > start)
    return np.where(ok, np.maximum(near, start), np.inf).min(-1, initial=np.inf)


def hit_walls(origin, dirs, half, start):
    with np.errstate(divide='ignore', invalid='ignore'):
        t = (np.sign(dirs) * half - origin[:, :, None]) / dirs
    # a creature squeezed a little into a wall starts its rays beyond it, which is a hit straight away
    return np.where(np.isfinite(t), np.maximum(t, start), np.inf).min(-1)
