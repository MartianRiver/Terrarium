# A scripted forager for the balance test only (never trained on, never copied into a brain). It knows where the
# food patches and meadows are, as perfect memory would, and carrier and nester don't: with nothing in view it walks to
# a known site (the nearer ones, spread over the colony by slot) and waits there for food to grow, leaves early enough to
# be home when night falls, and stays in until dawn. With grass, a hungry nim with an empty store grazes at night.

import numpy as np

from terrarium import vision
from terrarium.vision import FOOD, NOTHING, look
from terrarium.world import World

# seconds of slack on top of the walk home, and how many of the nearest sites the colony spreads over
MARGIN = 5.0
SPREAD = 3
# walking pace as a share of top speed (a crop slows it)
PACE = 0.85
ARRIVED = 0.8


def bearing_to(w: World, there: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Metres to a point (arenas, creatures, 2) and which way off the heading it lies."""
    gap = there - w.pos
    turn = np.arctan2(gap[..., 1], gap[..., 0]) - w.heading
    return np.hypot(gap[..., 0], gap[..., 1]), (turn + np.pi) % (2 * np.pi) - np.pi


def sites(w: World) -> np.ndarray | None:
    """(arenas, sites, 2): patch centres and meadow centres."""
    found = []
    if w.cfg.food.count and w.cfg.food.patches:
        found.append(w.patch_pos)
    if w.grass:
        found.append(w.grass.pos)
    return np.concatenate(found, 1) if found else None


def forager_policy(world: World):
    cfg = world.cfg
    angles = vision.angles(cfg.vision)
    ahead = np.abs(angles) < 0.5
    hz, night = cfg.tick_hz, cfg.night
    day = night.cycle - night.length
    slot = np.arange(len(world.colony)) % cfg.colonies.slots
    pace = cfg.creature.max_speed * PACE

    def act(w: World) -> np.ndarray:
        sight = look(w)
        food = np.where(sight.kind == FOOD, sight.dist, np.inf)
        sees = np.isfinite(food.min(-1))
        blocked = np.where(ahead & (sight.kind != NOTHING), sight.dist, np.inf).min(-1) < 1.5
        turn = np.where(sees, np.clip(angles[food.argmin(-1)] * 3, -1, 1), np.where(blocked, 1.0, 0.0))
        thrust = np.ones_like(turn)

        nest = w.nests[w.colony][None]
        dist_home, to_home = bearing_to(w, np.broadcast_to(nest, w.pos.shape))
        t = (w.age / hz + w.clock) % night.cycle
        left = np.where(w.dark, 0.0, day - t)[:, None]
        slow = 1 - cfg.crop.slow * w.crop
        leave = left < dist_home / (pace * slow) + MARGIN
        mine = np.take_along_axis(w.store, np.broadcast_to(w.colony, w.crop.shape), 1)
        hungry = w.energy < cfg.jelly.hunger
        at_nest = w.nest_at() == w.colony
        go_home = leave | (w.crop >= cfg.crop.capacity) | (hungry & (mine > 0))

        spots = sites(w)
        if spots is not None:
            # each colony's slots spread over its few nearest sites
            reach = np.hypot(*(spots[:, None] - w.nests[None, :, None]).transpose(3, 0, 1, 2))     # A,C,S
            order = reach.argsort(-1)[:, :, :SPREAD]                                              # A,C,K
            pick = np.take_along_axis(order[:, w.colony], (slot % order.shape[-1])[None, :, None], 2)[..., 0]
            target = np.take_along_axis(spots, pick[..., None], 1)
            dist, to_site = bearing_to(w, target)
            idle = ~sees & ~go_home
            there = idle & (dist < ARRIVED)
            turn = np.where(idle, np.clip(to_site * 3, -1, 1), turn)
            thrust = np.where(there, 0.0, thrust)
            turn = np.where(there, 0.0, turn)
        if w.grass:
            # nothing in the store and hungry in the dark: the nearest meadow
            meadow = w.grass.pos[:, None] - w.pos[:, :, None]
            near = np.take_along_axis(meadow, np.hypot(meadow[..., 0], meadow[..., 1]).argmin(-1)[..., None, None], 2)[:, :, 0]
            _, to_meadow = bearing_to(w, w.pos + near)
            graze = w.dark[:, None] & hungry & (mine <= 0)
            go_home = go_home & ~graze
            turn = np.where(graze, np.clip(to_meadow * 3, -1, 1), turn)

        turn = np.where(go_home, np.clip(to_home * 3, -1, 1), turn)
        # in the nest with nowhere to be: wait (dusk, night, early morning)
        thrust = np.where(go_home & at_nest & leave, 0.0, thrust)
        unload = np.where(at_nest & (w.crop > 0), 1.0, -1.0)
        eat = np.where(hungry | (w.energy <= 1 - cfg.energy.food), 1.0, -1.0)
        return np.stack([thrust, turn, unload, eat], -1)
    return act
