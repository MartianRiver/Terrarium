# Goes to the remembered tree: the displacement test of finding 0005. One nim a game; while it's down in the burrow
# storing its first apple the tree moves at least APART m, somewhere it can't be seen from home. The first trip out
# afterwards "goes to the old spot" if it comes within NEAR m of where the tree stood before it sees a block. Played
# twice on the same games, notes kept and notes wiped at that deposit: kept minus wiped is what the notes did.
# A port of research/2026-11-06-displace (run.py, displace.py), the first trip only.
from pathlib import Path

import numpy as np

from . import scatter
from .brain import load
from .config import Config
from .evals import brain_policy
from .vision import BLOCK
from .world import World

NEAR, FAR_OLD, APART, TRIES = 1.5, 3.0, 6.0, 30


def first_trip(cfg: Config, brain: Path, games: int, seed: int, wipe: bool) -> dict:
    """Per game: kind (1 the tree moved, 0 no deposit yet, -1 nowhere to move it, -2 in sight from home, so it stays),
    went (reached the old spot first), apples stored, and whether the old spot is far enough from the nest to count."""
    w = World(cfg, games, seed)
    old, kind = np.full((games, 2), np.nan), np.zeros(games, int)
    went, seen, trip = (np.zeros(games, bool) for _ in range(3))
    wipe_next = np.zeros((games, 1), bool)

    def sight(obs, held, notes):
        seen[:] |= trip & (obs.kinds.reshape(games, -1) == BLOCK).any(1)

    def wipe_on(world):
        def event(world):
            hit = wipe_next.copy()
            wipe_next[:] = False
            return hit
        return event

    act = brain_policy(brain, mode='drawn', watch=sight, wipe_on=wipe_on if wipe else None)(w)
    stored = w.stored[:, 0].copy()
    for _ in range(w.episode_ticks):
        w.step(act(w))
        first = np.flatnonzero((w.stored[:, 0] > stored) & (kind == 0))
        stored = w.stored[:, 0].copy()
        if len(first):
            move_tree(w, first, kind, old)
            moved = first[kind[first] == 1]
            trip[moved] = True
            wipe_next[moved] = True
        # the old spot counts while the new tree hasn't been seen, until the nim's next deposit ends the trip
        d = np.hypot(*(w.pos[:, 0] - w.nests[0] - old).T)
        went |= trip & ~seen & (d < NEAR)
        trip &= ~((w.stored[:, 0] > 1) | ~w.alive[:, 0])
        if w.ended.all():
            break
    return {'kind': kind, 'went': went, 'stored': w.stored[:, 0].copy(), 'far': np.hypot(*old.T) >= FAR_OLD}


def move_tree(w: World, idx: np.ndarray, kind: np.ndarray, old: np.ndarray):
    """The tree goes somewhere out of sight of home in each of these games (kind says how it went), redrawn up to
    TRIES times until it is far enough from where it stood."""
    ph, trunk = w.physics, w.cfg.tree.trunk
    here = ph.block_pos[idx, trunk].copy()
    old[idx] = here - w.nests[0]
    kind[idx] = np.where(w.tree.seen_from_home()[idx], -2, 0)
    pend = idx[kind[idx] == 0]
    angle = {a: ph.block_angle[a, trunk] for a in pend}
    real = ph.read
    ph.read = lambda: None          # scatter.move reads every arena each time; once a round is enough
    try:
        for _ in range(TRIES):
            if not len(pend):
                break
            for a in pend:
                scatter.move(w, int(a), trunk)
            ph.read = real
            ph.read()
            ph.read = lambda: None
            now = ph.block_pos[pend, trunk]
            ok = (np.hypot(*(now - here[np.searchsorted(idx, pend)]).T) >= APART) & ~w.tree.seen_from_home()[pend]
            kind[pend[ok]] = 1
            pend = pend[~ok]
        for a in pend:
            ph.shift([int(a)], [trunk], here[np.searchsorted(idx, a)][None], np.array([angle[a]]))
            kind[a] = -1
    finally:
        ph.read = real
    ph.read()
    for a in idx[kind[idx] == 1]:
        for f in np.nonzero(w.food_present[a] & w.apple)[0]:
            w._grow(a, f)


def displace(cfg: Config, brain: Path, games: int, seed: int, draws: int = 2000) -> dict:
    if not cfg.tree.on:
        return {'na': 'the world has no tree'}
    if load(brain)[0].shape['memory'] == 0:
        return {'na': 'the brain has no memory, so there are no notes to keep or wipe'}
    # the world puts the trunk's nominal spot on the nest's middle (scatter moves it), which the layout check refuses
    check, World._check_layout = World._check_layout, lambda self: None
    try:
        kept, wiped = (first_trip(cfg, brain, games, seed, wipe) for wipe in (False, True))
    finally:
        World._check_layout = check
    ok = (kept['kind'] == 1) & (wiped['kind'] == 1) & kept['far']
    n = int(ok.sum())
    if n == 0:
        return {'na': 'no game moved the tree out of sight', 'visible_at_start': int((kept['kind'] == -2).sum())}
    k, x = kept['went'][ok].astype(float), wiped['went'][ok].astype(float)
    pick = np.random.default_rng(7).integers(0, n, (draws, n))
    lo, hi = np.percentile(k[pick].mean(1) - x[pick].mean(1), [2.5, 97.5])
    minutes = cfg.episode.seconds / 60
    return {'trips': n, 'kept': round(float(k.mean()), 3), 'wiped': round(float(x.mean()), 3),
            'diff': round(float(k.mean() - x.mean()), 3), 'diff_ci': [round(float(lo), 3), round(float(hi), 3)],
            'visible_at_start': int((kept['kind'] == -2).sum()), 'no_spot': int((kept['kind'] == -1).sum()),
            'apples_min_kept': round(float(kept['stored'][ok].mean() / minutes), 2),
            'apples_min_wiped': round(float(wiped['stored'][ok].mean() / minutes), 2)}
