# The skills battery's tests (battery.py runs them): each plays one frozen brain in one world and measures one skill.
# graze and pond are ports of the probes behind 0031 (anchor_probe.py) and 0030 (still_probe.py), night of the
# 11 Nov deaths autopsy (lab/2026-11-11-deaths), tree counts apples from the World.
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .body import CAUSES
from .config import Config
from .evals import brain_policy
from .world import World


def play(cfg: Config, brain: Path, games: int, seed: int, mode: str, before_step: Callable | None = None,
         after_step: Callable | None = None) -> World:
    """The brain frozen in `games` games to their end. The hooks get (world, alive): who is alive in an unfinished
    game when the tick begins, before the step and after it."""
    w = World(cfg, games, seed)
    act = brain_policy(brain, mode=mode)(w)
    for _ in range(w.episode_ticks):
        alive = w.alive & ~w.ended[:, None]
        if before_step:
            before_step(w, alive)
        w.step(act(w))
        if after_step:
            after_step(w, alive)
        if w.ended.all():
            break
    return w


def cohort_alive(w: World) -> np.ndarray:
    """(arenas, creatures): the nims the game started with that are still alive, by id. A hatchling in a slot has a new
    id, and a spare slot started empty, so neither counts."""
    start = np.arange(1, w.alive.shape[1] + 1)
    return w.alive & ~w.spare & (w.creature_id == start)


def survival(w: World) -> dict:
    """The three things a headcount mixes up: `alive` is the share of the starting cohort still alive, `living` the
    nims alive at the end a game (cohort and hatched), `cohort` how many started, and `colonies_alive` the share of
    colonies with anyone alive."""
    games = w.alive.shape[0]
    starts = int((~w.spare).sum())
    colonies = np.stack([w.alive[:, w.colony == c].any(1) for c in range(len(w.nests))], 1)
    return {'alive': round(float(cohort_alive(w).sum() / (games * starts)), 3),
            'living': round(float(w.alive.sum() / games), 2), 'cohort': starts,
            'colonies_alive': round(float(colonies.mean()), 3),
            'alive_is': 'share of the starting nims still alive by id; living is a headcount with hatchlings'}


def spells(mask: np.ndarray) -> np.ndarray:
    """How many ticks each run of True lasts along axis 0 of mask (ticks, ...), one entry a run."""
    m = np.moveaxis(mask, 0, -1)
    pad = np.zeros((*m.shape[:-1], 1), bool)
    d = np.diff(np.concatenate([pad, m, pad], -1).astype(np.int8), axis=-1)
    return (np.argwhere(d == -1)[:, -1] - np.argwhere(d == 1)[:, -1]).astype(float)


def pcts(x, at=(10, 50, 90)) -> list[float] | None:
    return [round(float(v), 2) for v in np.percentile(x, at)] if len(x) else None


# stands to graze: share of meadow time anchored (within REACH of where it stood for the next HOLD s, 0031)

HOLD, REACH = 3.0, 0.25


def graze(cfg: Config, brain: Path, games: int, seed: int, mode: str = 'sampled') -> dict:
    if not cfg.grass.on:
        return {'na': 'the world has no meadows'}
    pos_l, inm_l, live_l, speed_l = [], [], [], []

    def look(w, before):
        near = np.hypot(*(w.pos[:, :, None, :] - w.grass.pos[:, None, :, :]).transpose(3, 0, 1, 2)) < cfg.grass.radius
        pos_l.append(w.pos.copy())
        inm_l.append(near.any(-1) & before)
        live_l.append(before.copy())
        speed_l.append(np.hypot(*w.vel.transpose(2, 0, 1)))

    play(cfg, brain, games, seed, mode, after_step=look)
    pos, inm, live, speed = (np.array(x) for x in (pos_l, inm_l, live_l, speed_l))
    k, T = round(HOLD / cfg.dt), len(pos)
    # anchored[t]: inside REACH of pos[t] for ticks t..t+k, alive and in a meadow throughout
    anchored = np.zeros(inm.shape, bool)
    if T > k:
        ok = np.ones((T - k, *inm.shape[1:]), bool)
        for j in range(k + 1):
            ok &= (np.hypot(*(pos[j:T - k + j] - pos[:T - k]).transpose(3, 0, 1, 2)) <= REACH) & inm[j:T - k + j]
        anchored[:T - k] = ok
    covered = np.zeros_like(anchored)
    for j in range(k + 1):
        covered[j:] |= anchored[:T - j]
    # a stretch's extent is the diagonal of the box around everywhere it went: chained windows let a slow crawl count
    lengths, extent = [], []
    run = np.zeros(inm.shape[1:])
    lo, hi = np.zeros((*inm.shape[1:], 2)), np.zeros((*inm.shape[1:], 2))
    for t in range(T):
        done = (run > 0) & ~covered[t]
        lengths += list(run[done])
        extent += list(np.hypot(*(hi - lo)[done].T))
        fresh = covered[t] & (run == 0)
        lo = np.where(fresh[..., None], pos[t], np.minimum(lo, pos[t]))
        hi = np.where(fresh[..., None], pos[t], np.maximum(hi, pos[t]))
        run = np.where(covered[t], run + cfg.dt, 0)
    lengths += list(run[run > 0])
    extent += list(np.hypot(*(hi - lo)[run > 0].T))
    lengths, extent = np.array(lengths), np.array(extent)
    meadow = max(int(inm.sum()), 1)
    return {'meadow_share': round(float(inm.sum() / max(live.sum(), 1)), 3),
            'anchored': round(float(covered.sum() / meadow), 3),
            'stretch_s': pcts(lengths), 'stretches_10s': int((lengths >= 10).sum()),
            'extent_m': pcts(extent),
            'meadow_speed': round(float(np.median(speed[inm])), 2) if inm.any() else None}


# drinks still: how fast it goes in the pond and how long it stays (0030)

def pond(cfg: Config, brain: Path, games: int, seed: int, mode: str = 'sampled') -> dict:
    if not cfg.water.on:
        return {'na': 'the world has no pond'}
    inside_l, speed_l, sipped_l, live_l = [], [], [], []
    drank = np.zeros((games, 1))

    # inside and speed are read before the step, as still_probe did: the velocity the tick began with
    def pre(w, alive):
        inside_l.append(w.ponds.inside() & alive)
        speed_l.append(np.hypot(*w.vel.transpose(2, 0, 1)))

    def post(w, alive):
        nonlocal drank
        sipped_l.append((w.drank > drank) & alive)
        drank = w.drank.copy()
        live_l.append(alive.copy())

    w = play(cfg, brain, games, seed, mode, pre, post)
    inside, speed, sipped, live = (np.array(x) for x in (inside_l, speed_l, sipped_l, live_l))
    visits = spells(inside) * cfg.dt
    secs = live.sum() * cfg.dt
    # of the nims that started, who never stood in the pond; water is in bars of a full one, as it was drunk
    starting = ~w.spare
    never = ~inside.any(0)[:, starting]
    thirst = w.died_counts[:, CAUSES.index('thirst')].sum()
    return {'pond_speed': round(float(np.median(speed[inside])), 2) if inside.any() else None,
            'visits': len(visits), 'visit_s': pcts(visits), 'visits_4s': int((visits >= 4).sum()),
            'longest_s': round(float(visits.max()), 1) if len(visits) else 0.0,
            'drink_s_game': round(float(sipped.sum() * cfg.dt / games), 1),
            'drink_s_min': round(float(sipped.sum() * cfg.dt / (secs / 60)), 1) if secs else None,
            'alive_s_game': round(float(secs / games), 1),
            'water_game': round(float(w.drank.sum() / games), 2),
            'water_visit': round(float(w.drank.sum() / len(visits)), 3) if len(visits) else None,
            'never_pond': round(float(never.mean()), 3),
            'thirst_deaths': round(float(thirst / (games * starting.sum())), 3)}


# jumps for apples: apples taken from the tree and brought home a minute of a living nim's time (berries don't count)

def tree(cfg: Config, brain: Path, games: int, seed: int, mode: str = 'drawn') -> dict:
    if not cfg.tree.on:
        return {'na': 'the world has no tree'}
    live = []
    w = play(cfg, brain, games, seed, mode, after_step=lambda w, alive: live.append(alive.copy()))
    minutes = np.sum(live) * cfg.dt / 60
    return {'picked_min': round(float(w.apples_taken.sum() / minutes), 2),
            'home_min': round(float(w.apples_stored.sum() / minutes), 2),
            'jumps_min': round(float(w.jumps.sum() / minutes), 2), **survival(w)}


# stays home at night: alive at the end, and how still it is at home in the dark, and how often it leaves

STILL = 0.2


def night(cfg: Config, brain: Path, games: int, seed: int, mode: str = 'drawn') -> dict:
    if not cfg.night.on:
        return {'na': 'the world has no nights'}
    rows_l, exits_l = [], []
    was_home = []

    def pre(w, alive):
        was_home[:] = [w.nest_at() == w.colony]

    def post(w, alive):
        dark = alive & w.dark[:, None]
        home = w.nest_at() == w.colony
        still = np.hypot(*w.vel.transpose(2, 0, 1)) < STILL
        rows_l.append(np.stack([dark, dark & home, dark & home & still]))
        # an exit is a tick that began at home and ended outside, in the dark
        exits_l.append(dark & was_home[0] & ~home)

    w = play(cfg, brain, games, seed, mode, pre, post)
    rows, exits = np.array(rows_l), np.array(exits_l)
    dark_s, home_s, still_s = (rows[:, i].sum() * cfg.dt for i in range(3))
    return {**survival(w),
            'still_home': round(float(still_s / dark_s), 3) if dark_s else None,
            'still_when_home': round(float(still_s / home_s), 3) if home_s else None,
            'home_share': round(float(home_s / dark_s), 3) if dark_s else None,
            'exits_night': round(float(exits.sum() / (dark_s / cfg.night.length)), 2) if dark_s else None}
