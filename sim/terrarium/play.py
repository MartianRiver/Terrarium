# Play as one Terrikin among a brain's own: one arena of a run's world, every other Terrikin steered by one of the
# run's checkpoints exactly as evals and replays steer it, and one, yours, steered by what the viewer sends. The game
# only moves when the viewer asks for the next few ticks, so it plays at the viewer's pace and pauses with it.
#
# Scored the way evals score a brain: food a minute alive and seconds alive, yours beside the brain's Terrikins'.
# When yours dies, its place is the brain's again (a hatchling there is one of theirs), and you watch to the end.

import secrets
import threading
import time
from pathlib import Path

import numpy as np

from . import replay
from .brain import brain_id
from .config import Config
from .evals import brain_policy
from .schema import ACTIONS
from .world import World

# what each yes/no action needs from the world to do anything
NEEDS = {
    'unload': lambda c: c.crop.capacity > 0,
    'eat': lambda c: c.crop.capacity > 0,
    'sprint': lambda c: c.sprint.on,
    'grab': lambda c: c.grab.on,
}
GAMES = 4
IDLE = 600


class Game:
    def __init__(self, cfg: Config, brain: Path, seed: int, label: str):
        self.world = w = World(cfg, 1, seed)
        self.act = brain_policy(brain)(w)
        self.hz = cfg.tick_hz
        starters = np.flatnonzero((w.colony == 0) & ~w.spare)
        self.slot = int(starters[0])
        self.you = int(w.creature_id[0, self.slot])
        self.lived = np.zeros(len(w.colony), int)
        self.controls = [a for a in ACTIONS[2:] if a in NEEDS and NEEDS[a](cfg)]
        self.used = time.time()
        source = {'seed': seed, 'brain': {'id': brain_id(brain), 'file': brain.name}, 'play': label}
        self.header = replay.header(w, 0, source)
        self.first = replay.frame(w, 0)

    @property
    def playing(self) -> bool:
        """Yours is still alive, and still yours (not a hatchling in its place)."""
        w = self.world
        return bool(w.alive[0, self.slot] and w.creature_id[0, self.slot] == self.you)

    def step(self, ticks: int, thrust: float, turn: float, yes: list[str]) -> list[dict]:
        w, frames = self.world, []
        self.used = time.time()
        for _ in range(ticks):
            if w.ended[0]:
                break
            actions = self.act(w).copy()
            if self.playing:
                mine = np.full(len(ACTIONS), -1.0)
                mine[0], mine[1] = np.clip(thrust, -1, 1), np.clip(turn, -1, 1)
                for name in yes:
                    if name in self.controls:
                        mine[ACTIONS.index(name)] = 1.0
                actions[0, self.slot] = mine[:actions.shape[-1]]
            self.lived += w.alive[0]
            w.step(actions)
            frames.append(replay.frame(w, 0))
        return frames

    def score(self) -> dict:
        w = self.world
        minutes = self.lived / self.hz / 60
        theirs = ~w.spare & (np.arange(len(w.colony)) != self.slot)
        alive = w.alive[0]
        return {
            'you': {'alive': self.playing, 'seconds': round(float(self.lived[self.slot]) / self.hz, 1),
                    'meals': int(w.meals[0, self.slot]), 'energy': round(float(w.energy[0, self.slot]), 3),
                    'per_minute': round(float(w.meals[0, self.slot] / max(minutes[self.slot], 1e-9)), 2)},
            # in a world of one there's nobody else to compare with
            'brain': {'seconds': round(float(self.lived[theirs].mean()) / self.hz, 1) if theirs.any() else 0.0,
                      'per_minute': round(float(w.meals[0, theirs].sum() / max(minutes[theirs].sum(), 1e-9)), 2)},
            'colonies': [int((alive & (w.colony == c)).sum()) for c in range(w.cfg.colonies.count)],
            'seconds': round(float(w.age[0]) / self.hz, 1), 'length': round(float(w.episode_ticks) / self.hz, 1),
            'over': bool(w.ended[0]),
        }


class Games:
    """The games going on this machine, by a token the viewer that started each one holds."""

    def __init__(self):
        self.games: dict[str, Game] = {}
        self.lock = threading.Lock()

    def start(self, cfg: Config, brain: Path, seed: int, label: str) -> tuple[str, Game]:
        game = Game(cfg, brain, seed, label)
        token = secrets.token_urlsafe(12)
        with self.lock:
            now = time.time()
            for old in [t for t, g in self.games.items() if now - g.used > IDLE]:
                del self.games[old]
            while len(self.games) >= GAMES:
                del self.games[min(self.games, key=lambda t: self.games[t].used)]
            self.games[token] = game
        return token, game

    def get(self, token: str) -> Game | None:
        with self.lock:
            return self.games.get(token)
