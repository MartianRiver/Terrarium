# Where a Terrikin's notes put the tree. A memory brain's notes (the GRU state) hold a straight-line trace of where the
# tree is: at the first choice after it unloads an apple and comes up out of the nest, a ridge regression on the notes
# gives the tree's offset from the nest to a metre or two, when the trunk isn't in sight. The readout is fitted on a
# frozen brain playing a world, per brain, and the recorder (`record --ghost`) writes what it reads for the viewer to
# draw as a faint tree. It is only checked at that moment, so that is the only moment it is shown.
#
#   uv run python -m terrarium.ghost fit RUN_OR_PT --world W.toml --games 3000 --seed S --out readout.npz

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import replay
from .brain import brain_id, load as load_brain
from .config import Config, build, load, upgrade
from .evals import brain_policy
from .log import Logger
from .vision import BLOCK
from .world import World

log = Logger('ghost')

# seconds a ghost shows after the Terrikin comes up, if it hasn't an apple in its crop by then
SHOW = 20.0
ALPHAS = np.logspace(-1, 4.5, 12)
FOLDS = 5
# share of the games kept back to score the fit on
HELD_OUT = 0.2


@dataclass
class Readout:
    brain: str
    world: str
    games: int
    seed: int
    keep: np.ndarray        # which of the notes vary, (memory,) bool
    mean: np.ndarray        # of the kept notes, on the fit set
    scale: np.ndarray
    weights: np.ndarray     # (kept, 2)
    intercept: np.ndarray   # (2,)
    alpha: float
    median_m: float         # on games held out of the fit, trunk not in sight
    median_deg: float
    held_out: int           # samples that median is over

    def apply(self, notes: np.ndarray) -> np.ndarray:
        """Notes (n, memory) to the tree's offset from the nest (n, 2), in the world's frame."""
        x = (np.asarray(notes, dtype=np.float64)[:, self.keep] - self.mean) / self.scale
        return x @ self.weights + self.intercept

    def save(self, path: Path | str):
        arrays = {k: getattr(self, k) for k in ('keep', 'mean', 'scale', 'weights', 'intercept')}
        meta = {k: getattr(self, k) for k in ('brain', 'world', 'games', 'seed', 'alpha', 'median_m', 'median_deg', 'held_out')}
        np.savez(path, meta=json.dumps(meta), **arrays)

    @classmethod
    def load(cls, path: Path | str) -> 'Readout':
        with np.load(path) as z:
            return cls(**json.loads(str(z['meta'])), **{k: z[k] for k in ('keep', 'mean', 'scale', 'weights', 'intercept')})


def ridge(x: np.ndarray, y: np.ndarray, alpha: float):
    """Standardise on x, then fit: the kept columns, their mean and scale, weights and intercept."""
    mu, sd = x.mean(0), x.std(0)
    keep = sd > 1e-8
    a = (x[:, keep] - mu[keep]) / sd[keep]
    ym = y.mean(0)
    w = np.linalg.solve(a.T @ a + alpha * np.eye(a.shape[1]), a.T @ (y - ym))
    return keep, mu[keep], sd[keep], w, ym


def pick_alpha(x: np.ndarray, y: np.ndarray, game: np.ndarray) -> float:
    """The alpha with the least squared error over folds of whole games."""
    games, at = np.unique(game, return_inverse=True)
    fold = (np.random.default_rng(1).permutation(len(games)) % FOLDS)[at]
    err = np.zeros(len(ALPHAS))
    for k in range(FOLDS):
        tr, va = fold != k, fold == k
        mu, sd = x[tr].mean(0), x[tr].std(0)
        keep = sd > 1e-8
        a, b = (x[tr][:, keep] - mu[keep]) / sd[keep], (x[va][:, keep] - mu[keep]) / sd[keep]
        # one eigendecomposition a fold, every alpha from it
        ev, vec = np.linalg.eigh(a.T @ a)
        ym = y[tr].mean(0)
        proj = vec.T @ (a.T @ (y[tr] - ym))
        for i, alpha in enumerate(ALPHAS):
            err[i] += (((b @ vec) @ (proj / (ev + alpha)[:, None]) + ym - y[va]) ** 2).sum()
    return float(ALPHAS[err.argmin()])


def bearing_error(pred: np.ndarray, true: np.ndarray) -> np.ndarray:
    """Degrees between where two offsets point."""
    turn = np.arctan2(pred[:, 1], pred[:, 0]) - np.arctan2(true[:, 1], true[:, 0])
    return np.degrees(np.abs(np.angle(np.exp(1j * turn))))


def fit_notes(notes: np.ndarray, tree: np.ndarray, game: np.ndarray, brain: str = '', world: str = '', seed: int = 0) -> Readout:
    """The readout from notes and the tree's offset at each sample, scored on a fifth of the games kept back."""
    x, y = notes.astype(np.float64), tree.astype(np.float64)
    games = np.unique(game)
    test_games = np.random.default_rng(2).permutation(games)[:max(1, int(HELD_OUT * len(games)))]
    test = np.isin(game, test_games)
    part = Readout('', '', 0, 0, *ridge(x[~test], y[~test], pick_alpha(x[~test], y[~test], game[~test])), 0.0, 0.0, 0.0, 0)
    pred = part.apply(x[test])
    median_m = float(np.median(np.hypot(*(pred - y[test]).T)))
    median_deg = float(np.median(bearing_error(pred, y[test])))
    alpha = pick_alpha(x, y, game)
    return Readout(brain, world, len(games), seed, *ridge(x, y, alpha), alpha, median_m, median_deg, int(test.sum()))


def collect(brain: Path | str, cfg: Config, games: int, seed: int):
    """Play `games` games with the brain frozen. At each choice right after a deposit with no block in sight: the
    notes it goes into, the tree's offset from its nest, and the game."""
    world = World(cfg, games, seed)
    if not world.tree:
        raise ValueError('the world has no tree ([tree])')
    n = world.alive.shape[1]
    rows: dict[str, list] = {'notes': [], 'tree': [], 'game': []}
    stored = world.stored.copy()

    def watch(obs, held, notes):
        nonlocal stored
        up = (world.stored > stored).reshape(-1)
        stored = world.stored.copy()
        seen = (obs.kinds.reshape(len(up), -1) == BLOCK).any(1)
        at = np.flatnonzero(up & ~seen)
        if not len(at):
            return
        a, c = np.divmod(at, n)
        rows['notes'].append(notes[at].cpu().numpy())
        rows['tree'].append(world.physics.block_pos[a, cfg.tree.trunk] - world.nests[world.colony[c]])
        rows['game'].append(a)

    act = brain_policy(brain, watch=watch)(world)
    for _ in range(world.episode_ticks):
        world.step(act(world))
    if not rows['game']:
        raise ValueError('no deposits out of sight of a block: nothing to fit')
    return {k: np.concatenate(v) for k, v in rows.items()}


def fit(brain: Path | str, cfg: Config, games: int, seed: int, world: str = '') -> Readout:
    if not load_brain(brain)[0].memory:
        raise ValueError('the brain has no memory: no notes to read')
    got = collect(brain, cfg, games, seed)
    log.info('collected', games=games, samples=len(got['game']))
    return fit_notes(got['notes'], got['tree'], got['game'], brain_id(brain), world, seed)


class Trail:
    """Where the notes put the tree for each Terrikin that has come up out of its nest, from that choice until it has an
    apple in its crop again or SHOW seconds pass: what a replay's `ghosts` hold."""

    def __init__(self, readout: Readout, world: World):
        self.readout = readout
        self.world = world
        self.stored = world.stored.copy()
        self.at = np.zeros((*world.alive.shape, 2))
        self.until = np.zeros(world.alive.shape, int)

    def surface(self, up: np.ndarray, notes: np.ndarray):
        """These (arenas, creatures) have just unloaded; notes are all the creatures' (arenas * creatures, memory)."""
        w = self.world
        rows = np.flatnonzero(up.reshape(-1))
        if not len(rows):
            return
        a, c = np.divmod(rows, up.shape[1])
        self.at[a, c] = w.nests[w.colony[c]] + self.readout.apply(notes[rows])
        self.until[a, c] = w.tick + round(SHOW * w.cfg.tick_hz)

    def watch(self, obs, held, notes):
        """For evals.brain_policy's `watch`: called at every choice, before the step."""
        up = self.world.stored > self.stored
        self.stored = self.world.stored.copy()
        self.surface(up, notes.cpu().numpy())

    def frame(self, a: int) -> list[dict]:
        """Arena a's ghosts for the frame just made; an apple in the crop ends one for good."""
        w = self.world
        self.until[a, w.crop[a] > 0] = 0
        live = (w.tick < self.until[a]) & w.alive[a]
        return [{'id': int(w.creature_id[a, c]), 'x': round(float(self.at[a, c, 0]), replay.DIGITS), 'y': round(float(self.at[a, c, 1]), replay.DIGITS)}
                for c in np.flatnonzero(live)]


def resolve(path: str) -> tuple[Path, Path | None]:
    """A checkpoint, and its run's folder if it sits in one: the path itself, or the newest checkpoint of a run."""
    p = Path(path)
    if p.suffix == '.pt':
        run = p.parent.parent if p.parent.name == 'checkpoints' else None
        return p, run
    run = p.parent if p.name == 'checkpoints' else p
    return sorted((run / 'checkpoints').glob('*.pt'))[-1], run


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fit', help='play a frozen brain, read the tree off its notes, save the readout')
    f.add_argument('brain', help='a checkpoint, or a run (its newest checkpoint)')
    f.add_argument('--world', help='a world file; default the world the run trained in (its run.json)')
    f.add_argument('--games', type=int, default=3000)
    f.add_argument('--seed', type=int, required=True)
    f.add_argument('--out', required=True)
    f.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()

    import torch
    torch.set_num_threads(args.threads)
    pt, run = resolve(args.brain)
    if args.world:
        cfg, label = load(args.world), args.world
    elif run and (run / 'run.json').exists():
        saved = json.loads((run / 'run.json').read_text())['world']
        cfg, label = build(Config, upgrade(saved['config'])), f"{run.name} run.json ({saved.get('file', '')})"
    else:
        parser.error('no run.json beside that checkpoint: give --world')
    readout = fit(pt, cfg, args.games, args.seed, label)
    readout.save(args.out)
    print(f'{pt.name} ({readout.brain[:12]}) in {label}: {readout.games} games, seed {args.seed}; held out '
          f'{readout.held_out} samples: median {readout.median_m:.2f} m, {readout.median_deg:.1f} deg (alpha {readout.alpha:.3g})')


if __name__ == '__main__':
    main()
