# Fixed games played with fixed actions, for checking that every body dial left at its default plays exactly as the
# code did before [fat], [energy] rest/sleep/work and the death causes existed (c19e080). data/body_off.npz holds what
# that code did; test_body.py plays the same games on today's and compares.
#
# To make the file again (only if a change that isn't the body's is meant to change these games): extract c19e080's
# sim/terrarium and sim/configs somewhere, then from there
#   PYTHONPATH=<there>/sim python <this file> <there>/sim/configs data/body_off.npz
# and look at that the old code's output is what the file holds.
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from terrarium import load
from terrarium.world import World

# what's recorded every SNAP ticks; the body's own fields (fat, died_of) are left out, they didn't exist
FIELDS = ('pos', 'vel', 'heading', 'energy', 'alive', 'unborn', 'crop', 'store', 'stamina', 'water', 'chill', 'fed',
          'nourished', 'spent', 'meals', 'jelly', 'hatched', 'young', 'grazed', 'drunk', 'jumps', 'stored')
SNAP = 40


def short_cycle(cfg):
    return replace(cfg, night=replace(cfg.night, cycle=30.0, length=15.0, cold=0.04))


def hungry(cfg, start=0.5, drain=0.03):
    return replace(cfg, energy=replace(cfg.energy, start=start, drain=drain))


def stocked(world):
    """A full store, so there's jelly to eat and eggs to hatch, and nims that are hungry for it."""
    world.store[:] = 30.0
    world.energy[:] = np.where(world.alive, np.linspace(0.2, 0.7, world.energy.shape[1]), 0.0)


def loaded(world):
    """Every other nim starts with a full crop and a full bar, so some eat from the crop and some unload it at home."""
    world.crop[:, ::2] = world.cfg.crop.capacity


# name, config file, change to it, arenas, ticks, tick to reset arena 0 at (0: never), set-up
GAMES = (
    ('feeding', 'solo.toml', lambda c: hungry(c, 0.6, 0.004), 2, 600, 0, None),
    ('running out', 'solo.toml', lambda c: hungry(replace(c, food=replace(c.food, count=0)), 0.3, 0.05), 2, 500, 0, None),
    ('night and dawn', 'night.toml', short_cycle, 2, 1300, 0, None),
    ('reset', 'night.toml', lambda c: hungry(short_cycle(c), 0.5, 0.01), 2, 900, 450, None),
    ('hatching', 'colony-young.toml', lambda c: short_cycle(hungry(c, 0.6, 0.01)), 2, 1500, 0, stocked),
    ('flowers and crop', 'colony-feast.toml', lambda c: hungry(c, 0.95, 0.01), 2, 1200, 0, loaded),
    ('water', 'nursery-water.toml', lambda c: hungry(c, 0.7, 0.01), 2, 800, 0, None),
    ('grass', 'nursery-grass.toml', lambda c: hungry(c, 0.5, 0.02), 2, 600, 0, None),
    ('tree', 'nursery-tree-home.toml', lambda c: hungry(c, 0.6, 0.02), 2, 600, 0, None),
)


def actions(world, rng):
    """A forager that doesn't think: carries what it has home and unloads and eats there, else walks at the nearest
    food, open flower or meadow, pressing every other button now and then."""
    a, n = world.pos.shape[:2]
    # one far-off place that's never there, so a world without food still has a nearest
    spots = [world.food_pos, np.zeros((a, 1, 2))]
    live = [world.food_present, np.zeros((a, 1), bool)]
    if world.cfg.flowers.on:
        spots.append(world.flower_pos)
        live.append(world.flowers_open)
    if world.grass:
        spots.append(world.grass.pos)
        live.append(np.ones(world.grass.pos.shape[:2], bool))
    spot, here = np.concatenate(spots, 1), np.concatenate(live, 1)
    gap = spot[:, None] - world.pos[:, :, None]
    near = np.where(here[:, None], np.hypot(gap[..., 0], gap[..., 1]), np.inf)
    pick = near.argmin(2)
    food = np.take_along_axis(gap, pick[..., None, None], 2)[:, :, 0]
    home = world.nests[world.colony][None] - world.pos
    go = np.where((world.crop > 0)[..., None], home, food)
    err = (np.arctan2(go[..., 1], go[..., 0]) - world.heading + np.pi) % (2 * np.pi) - np.pi
    x = np.where(rng.random((a, n, 8)) < 0.2, 1.0, -1.0)
    x[..., 0] = np.where(np.isfinite(near.min(2)) | (world.crop > 0), 1.0, 0.3)
    x[..., 1] = np.clip(err * 2, -1, 1)
    x[..., 2:4] = 1.0
    return x


def play(cfg, arenas, ticks, reset_at, prep, seed=3):
    world = World(cfg, arenas, seed)
    rng = np.random.default_rng(seed)
    if prep:
        prep(world)
    out = {k: [] for k in FIELDS if hasattr(world, k)}
    for t in range(ticks):
        if reset_at and t == reset_at:
            world.reset(np.array([0]))
        world.step(actions(world, rng))
        if t % SNAP == 0:
            for k in out:
                out[k].append(np.array(getattr(world, k), copy=True))
    return {k: np.stack(v) for k, v in out.items()}


def record(configs: Path) -> dict[str, np.ndarray]:
    trace = {}
    for name, file, change, arenas, ticks, reset_at, prep in GAMES:
        for k, v in play(change(load(configs / file)), arenas, ticks, reset_at, prep).items():
            trace[f'{name}/{k}'] = v
    return trace


if __name__ == '__main__':
    np.savez_compressed(sys.argv[2], **record(Path(sys.argv[1])))
