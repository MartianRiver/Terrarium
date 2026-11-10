# The supply ratio: how much food a world grows in a day and its night, against what its starting colonies need.
#
# supply = foods the standing food could give at most + foods' worth of grass, per day-plus-night
# need   = starting nims x energy each spends in that cycle / energy in one food
#
# Both are ceilings and bookkeeping, not forecasts: a food that grows is eaten the moment it appears (no slot
# waits, nobody walks), and the walking is a flat share of the day (`duty`) at full thrust. What the colonies
# really pick is measured against the supply ceiling in the runs (harvest).

from dataclasses import replace

import numpy as np

from terrarium.config import Config

# share of the day a nim spends at full thrust: a guess, and the one number in the need that isn't in the config
DUTY = 0.5


def cycle_length(cfg: Config) -> float:
    return cfg.night.cycle if cfg.night.on else 120.0


def day_length(cfg: Config) -> float:
    return cfg.night.cycle - cfg.night.length if cfg.night.on else 120.0


def starting_nims(cfg: Config) -> int:
    return cfg.colonies.count * cfg.colonies.size


def need(cfg: Config, duty: float = DUTY) -> float:
    """Foods the starting nims eat in a cycle: drain all through it, walking by day, none of the cold (the nest keeps it off)."""
    e = cfg.energy
    each = e.drain * cycle_length(cfg) + e.move * duty * day_length(cfg)
    return starting_nims(cfg) * each / e.food


def wait(cfg: Config) -> float:
    return (cfg.food.regrow_min + cfg.food.regrow_max) / 2


def food_grown(cfg: Config) -> float:
    """The most foods the slots can grow in a day: nothing grows at night, and every slot waits afresh at dawn."""
    return cfg.food.count * day_length(cfg) / wait(cfg)


def grass_foods(cfg: Config) -> float:
    """Foods' worth of grass a cycle: every cell in a meadow (all of them, with a base cover) regrows `regrow` a second."""
    g = cfg.grass
    if not g.meadows and g.base <= 0:
        return 0.0
    cells = cfg.arena.size ** 2 / g.cell ** 2 if g.base > 0 else g.meadows * np.pi * g.radius ** 2 / g.cell ** 2
    return float(cells * g.regrow * cycle_length(cfg) * g.food / cfg.energy.food)


def ratio(cfg: Config, duty: float = DUTY) -> float:
    return (food_grown(cfg) + grass_foods(cfg)) / need(cfg, duty)


def describe(cfg: Config, duty: float = DUTY) -> dict:
    return {'start': starting_nims(cfg), 'cycle': cycle_length(cfg), 'day': day_length(cfg), 'duty': duty,
            'need': need(cfg, duty), 'grown': food_grown(cfg), 'grass': grass_foods(cfg), 'ratio': ratio(cfg, duty)}


def fit(cfg: Config, target: float, by: str = 'count', duty: float = DUTY) -> Config:
    """cfg with one dial moved to land on this ratio: `count` of foods (a whole number, so the ratio lands near it) or
    `regrow`, both waits scaled together (exact). Grass stays as it is."""
    want = target * need(cfg, duty) - grass_foods(cfg)
    if want <= 0:
        raise ValueError(f'the grass alone is already past a supply ratio of {target}')
    f = cfg.food
    if by == 'count':
        return replace(cfg, food=replace(f, count=max(1, round(want * wait(cfg) / day_length(cfg)))))
    if by == 'regrow':
        s = f.count * day_length(cfg) / want / wait(cfg)
        return replace(cfg, food=replace(f, regrow_min=f.regrow_min * s, regrow_max=f.regrow_max * s))
    raise ValueError(f'unknown dial {by!r}: count or regrow')
