# Jumping ([jump], height 0 is off): the world's first step off the flat. Bodies
# still push each other about on the ground (physics.py is 2D), but each has a
# height above it too, so something hung up high, like an apple on a tree, can
# be reached by a hop. A yes to jump while standing launches it fast enough to
# rise `height` metres, and it comes down again under gravity, steering as it
# goes. Nothing bumps into anything up there: it's only how high it is.
import numpy as np

G = 9.81


def step(world, jump: np.ndarray):
    """jump (arenas, creatures): yes this tick."""
    cfg, j = world.cfg, world.cfg.jump
    up = jump & (world.z <= 0) & world.alive
    if up.any():
        world.vz[up] = np.sqrt(2 * G * j.height)
        cost = j.energy * np.where(world.young > 0, cfg.young.energy, 1.0) * up
        world.spent += cost
        world.energy = np.clip(world.energy - cost, 0, 1)
        world.jumps += up
    flying = (world.z > 0) | up
    # exactly where gravity has it, so the top of a jump is its height and no higher
    world.z[flying] += world.vz[flying] * cfg.dt - G * cfg.dt ** 2 / 2
    world.vz[flying] -= G * cfg.dt
    landed = world.z <= 0
    world.z[landed] = 0
    world.vz[landed] = 0
