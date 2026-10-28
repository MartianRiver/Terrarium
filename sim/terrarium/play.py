# Play as one Terrikin among a brain's own: one arena of a run's world, every other Terrikin steered by one of the
# run's checkpoints exactly as evals and replays steer it, and one, yours, steered by what the viewer sends. The game
# only moves when the viewer asks for the next few ticks, so it plays at the viewer's pace and pauses with it.
#
# Scored like a game: points for every second alive, every berry picked up and every food brought home to the
# nest, yours beside the worst, average and best of the brain's Terrikins that started with you. When yours dies,
# its place is the brain's again (a hatchling there is one of theirs, and isn't scored), and you watch to the end.

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
    'carry': lambda c: c.carry.on,
}
# points for a second alive, a berry picked up, and a food brought home to its own nest
POINTS = {'second': 1, 'berry': 10, 'home': 20}
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
        # per Terrikin that started: ticks alive, berries picked up, food brought home
        self.started = [int(i) for i in w.creature_id[0, ~w.spare]]
        self.tally = {i: np.zeros(3) for i in self.started}
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
            ids, alive = w.creature_id[0].copy(), w.alive[0].copy()
            meals, stored = w.meals[0].copy(), w.stored[0].copy()
            w.step(actions)
            gained = np.stack([alive, np.maximum(w.meals[0] - meals, 0), np.maximum(w.stored[0] - stored, 0)], -1)
            for slot in np.flatnonzero(alive):
                if int(ids[slot]) in self.tally:
                    self.tally[int(ids[slot])] += gained[slot]
            frames.append(replay.frame(w, 0))
        return frames

    def card(self, who: int) -> dict:
        ticks, berries, home = self.tally[who]
        seconds = ticks / self.hz
        points = POINTS['second'] * seconds + POINTS['berry'] * berries + POINTS['home'] * home
        return {'seconds': round(float(seconds), 1), 'berries': int(berries), 'home': int(home), 'points': round(float(points))}

    def score(self) -> dict:
        w = self.world
        you = {**self.card(self.you), 'alive': self.playing, 'energy': round(float(w.energy[0, self.slot]), 3)}
        theirs = [self.card(i) for i in self.started if i != self.you]
        # in a world of one there's nobody else to compare with
        brain = {}
        if theirs:
            by = sorted(theirs, key=lambda c: c['points'])
            brain = {'worst': by[0], 'best': by[-1], 'count': len(theirs),
                     'average': {k: round(float(np.mean([c[k] for c in theirs])), 1) for k in by[0]}}
        alive = w.alive[0]
        return {
            'you': you, 'brain': brain, 'rank': 1 + sum(c['points'] > you['points'] for c in theirs),
            'points': POINTS,
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
