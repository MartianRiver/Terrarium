# Ray vision: a fan of rays from every creature in every arena at once, each
# giving how far it went and the kind of thing it hit first. Plain numpy on the
# positions physics reports. Rays start just outside the body, and anything
# already covering that point counts as hit there, as pymunk's queries do.
#
# Nests are flat ground, so they don't stop a ray: it says how far it went
# before reaching one, if that's before whatever it hit.

from dataclasses import dataclass

import numpy as np

from .world import World

NOTHING, WALL, CREATURE, FOOD, BLOCK, FLOWER = range(6)
# rays start this far outside the body, so a creature never sees itself
GAP = 0.01


def directions(heading, rays, fov):
    a = heading[..., None] + np.linspace(-fov / 2, fov / 2, rays)
    return np.stack([np.cos(a), np.sin(a)], -1)


@dataclass
class Sight:
    """All (arenas, creatures, rays), distances in metres from the creature's centre, at most the range."""
    dist: np.ndarray        # to the first thing hit
    kind: np.ndarray        # what that was
    nestmate: np.ndarray    # it's a creature from the same colony
    own_nest: np.ndarray    # to the edge of its colony's nest, the range when it hit something first
    other_nest: np.ndarray  # the same for any other colony's
    it: np.ndarray          # it's a creature that's it, in tag
    carrier: np.ndarray     # it's a creature carrying a flag


def look(world: World) -> Sight:
    cfg, v = world.cfg, world.cfg.vision
    start = cfg.creature.radius + GAP
    pos = world.pos
    arenas, n = pos.shape[:2]
    dirs = directions(world.heading, v.rays, v.fov)
    # the dead are gone from the world
    others = ~np.eye(n, dtype=bool) & world.alive[:, None, :]
    food = np.broadcast_to(world.food_seen[:, None], (arenas, n, world.food_present.shape[1]))
    flowers = np.broadcast_to(world.flowers_open[:, None], (arenas, n, world.flowers_open.shape[1]))
    half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2)
    creatures = hit_circles(pos, dirs, pos, cfg.creature.radius, others, start)
    hits = np.stack([
        hit_walls(pos, dirs, cfg.arena.size / 2, start),
        creatures.min(-1),
        hit_circles(pos, dirs, world.food_pos, cfg.food.radius, food, start).min(-1, initial=np.inf),
        hit_boxes(pos, dirs, world.block_pos, world.block_angle, half, start),
        hit_circles(pos, dirs, world.flower_pos, cfg.flowers.radius, flowers, start).min(-1, initial=np.inf),
    ], -1)
    dist = hits.min(-1)
    seen = dist < v.range
    dist, kind = np.where(seen, dist, v.range), np.where(seen, hits.argmin(-1) + WALL, NOTHING)
    hit = creatures.argmin(-1)
    theirs = world.colony[hit]
    nestmate = (kind == CREATURE) & (theirs == world.colony[:, None])
    it = (kind == CREATURE) & world.tag.mask()[np.arange(arenas)[:, None, None], hit] if world.tag else np.zeros_like(nestmate)
    carrier = (kind == CREATURE) & world.flags.carrying()[np.arange(arenas)[:, None, None], hit] if world.flags else np.zeros_like(nestmate)

    nests = np.broadcast_to(world.nests, (arenas, *world.nests.shape))
    every = np.ones((arenas, n, len(world.nests)), bool)
    reach = hit_circles(pos, dirs, nests, cfg.colonies.nest_radius, every, start)
    own = world.colony[:, None, None] == np.arange(len(world.nests))      # N,1,C
    own_nest, other_nest = (np.where(mask, reach, np.inf).min(-1) for mask in (own, ~own))
    return Sight(dist, kind, nestmate, *(np.where(t < dist, t, v.range) for t in (own_nest, other_nest)), it, carrier)


def hit_circles(origin, dirs, centres, radius, valid, start):
    """origin (A,N,2), dirs (A,N,R,2), centres (A,M,2), valid (A,N,M): where each ray hits each circle,
    (A,N,R,M), inf for none."""
    # x and y apart: einsum and sums over a length-2 axis are much slower in numpy
    ox = centres[:, None, :, 0] - origin[:, :, None, 0]             # A,N,M
    oy = centres[:, None, :, 1] - origin[:, :, None, 1]
    along = dirs[..., 0, None] * ox[:, :, None] + dirs[..., 1, None] * oy[:, :, None]
    miss2 = (ox * ox + oy * oy)[:, :, None] - along * along
    inside = radius * radius - miss2
    root = np.sqrt(np.maximum(inside, 0))
    ok = (inside > 0) & (along + root > start) & valid[:, :, None]
    return np.where(ok, np.maximum(along - root, start), np.inf)


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
