# What the body does to what it costs: resting and sleeping that burn less than walking ([energy] rest, sleep), moving by
# weight ([energy] work), fat kept beside energy ([fat]) and why a nim died. World calls these; each is off at its defaults.
import numpy as np

from . import night

# what a nim died of, as died_of keeps it (0: not dead); a predator is next. 'chilled' says what was true when its
# energy ran out (chill at CHILL or more), not that the cold did it: a nim chilled by the night that starves at home counts
CAUSES = ('', 'thirst', 'chilled', 'starved')
THIRST, CHILLED, STARVED = 1, 2, 3
CHILL = 0.5
# warm enough to sleep, and to rest the faster for it ([energy] sleep, [tired] warm)
WARM = 0.5


def kept(world) -> np.ndarray:
    """(arenas, creatures): the share of the cold kept off (night.warmth), worked out once a tick."""
    if world._kept_at[0] != world.tick:
        world._kept_at = (world.tick, night.warmth(world.pos, world.alive, world.colony, world.nest_at() == world.colony, world.cfg.night))
    return world._kept_at[1]


def warm(world) -> np.ndarray:
    """(arenas, creatures): who is warm enough to sleep, in its own nest or huddled."""
    return kept(world) >= WARM


def in_dark(world) -> np.ndarray:
    """(arenas,): whether it's night in the arena right now (world.dark lags a tick: nightfall sets it)."""
    return night.dark(world.age / world.cfg.tick_hz + world.clock, world.cfg.night)


def burn(world, thrust: np.ndarray) -> np.ndarray | float:
    """The share of `drain` each nim pays this tick: [energy] rest while it keeps still, sleep while it does in the
    dark and warm. Still is as [tired] has it when that's on."""
    e, t = world.cfg.energy, world.cfg.tired
    if e.rest == 1 and e.asleep == 1:
        return 1.0
    still = np.abs(thrust) < (t.still if t.on else e.still)
    asleep = still & in_dark(world)[:, None] & warm(world)
    return np.where(asleep, e.asleep, np.where(still, e.rest, 1.0))


def mass(world) -> np.ndarray:
    """(arenas, creatures) kg moving costs by: the body, its fat, what's in the crop and jaws, and a block it carries
    or holds."""
    cfg = world.cfg
    kg = cfg.creature.mass + world.fat * cfg.fat.heavy
    if cfg.crop.mass > 0:
        jaws = (world.load >= 0) | (world.dung.load >= 0 if world.dung else False)
        kg = kg + (world.crop + jaws) * cfg.crop.mass
    if cfg.block:
        weights = np.array([b.mass for b in cfg.block])
        kg = kg + np.where(world.block_load >= 0, weights[np.maximum(world.block_load, 0)], 0.0)
        for (a, i), joint in world.physics.held.items():
            kg[a, i] += joint.b.mass
    return kg


def burn_fat(world):
    """Below [fat] below, fat turns back into energy, up to `rate` a second. What a nim still owes (world.debt, spend
    that came due past empty) counts as energy it lacks, so fat pays that first, then the meals that came in, then the
    death check sees what's left."""
    f = world.cfg.fat
    short = np.maximum(f.below - (world.energy - world.debt), 0)
    back = np.minimum(np.minimum(world.fat, f.rate * world.cfg.dt), short) * world.alive
    world.energy += back
    world.fat -= back


def fat_room(world) -> np.ndarray | bool:
    """Who has room in their fat, so can eat with a full bar."""
    return world.fat < world.cfg.fat.capacity if world.cfg.fat.on else False


def settle(world):
    """Energy past full goes to fat, `keep` of it while there's room; the rest is lost. Then energy is clipped."""
    f = world.cfg.fat
    if f.on:
        world.fat += np.minimum(np.maximum(world.energy - 1, 0) * f.keep, f.capacity - world.fat)
    np.clip(world.energy, 0, 1, out=world.energy)


def record_deaths(world, dying: np.ndarray):
    """Why each of these nims died: out of water, else out of energy while chilled through, else out of energy."""
    dry = (world.water <= 0) if world.ponds else np.zeros_like(dying)
    cause = np.where(dry, THIRST, np.where(world.chill >= CHILL, CHILLED, STARVED))
    a, i = np.nonzero(dying)
    world.died_of[a, i] = cause[a, i]
    np.add.at(world.died_counts, (a, cause[a, i]), 1)
