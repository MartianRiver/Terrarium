# Catch them!, a game of tag for small children: you're always it, the rest are a tag brain's runners, and every one
# you touch is a catch. The caught one spins dizzy for a moment and can't be caught again straight away, so you go
# after another. You're faster than them, and the game watches how it's going: a long while without a catch slows
# the runners down a little, quick catches speed them back up, so a five-year-old and a ten-year-old both get a
# game they can win but have to work at.
#
# Every game is kept: its replay (where everyone went, you included) and a line in plays.jsonl saying how long it
# was played, every catch, how fast the runners ended up and why it stopped. That's for us to learn from (how long
# a mode holds them, where it gets too hard) and for scoring brains against children later; it never trains the
# brain we carry forward.

import dataclasses
import json
import time
from datetime import datetime
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from . import replay
from .config import DEFAULT, Config, load
from .log import Logger
from .play import Game
from .schema import ACTIONS

log = Logger('kids')


@dataclass(frozen=True)
class Mode:
    world: str
    runners: int
    seconds: float
    you: float      # your top speed, as a share of theirs
    reach: float    # how close counts as a touch (m between bodies): a little more than meeting is kinder
    dizzy: float    # seconds a caught one spins on the spot
    safe: float     # seconds before the one you caught can be caught again
    gap: float      # a catch about this often is going well; much longer and the runners slow down
    slowest: float  # the slowest the runners get, as a share of their top speed
    fastest: float
    start: float
    # catches for two stars and for three (two opens the next level): about 45% and 80% of what the sloppy pretend
    # player in the 0.4 notes catches
    stars: tuple[int, int]
    # snacks on the floor at once (0: none): each one eaten fills some of a turbo bar, and holding sprint runs on it
    snacks: int = 0


LITTLE = Mode('nursery-tag.toml', runners=6, seconds=90, you=1.35, reach=0.25, dizzy=2.0, safe=3.5, gap=5.0,
              slowest=0.35, fastest=0.9, start=0.6, stars=(6, 14), snacks=3)
BIG = Mode('nursery-tag-hide.toml', runners=6, seconds=90, you=1.3, reach=0.15, dizzy=1.5, safe=3.0, gap=6.0,
           slowest=0.45, fastest=0.8, start=0.6, stars=(10, 18))
MODES = {
    # the little room with two pillars, everyone in sight
    'little': (LITTLE,),
    # the room with blocks to hide behind, and a sprint (yours too), in levels: each a little less on your side,
    # the last in the playground (20 m, twenty-four blocks)
    'big': (BIG,
            replace(BIG, you=1.25, fastest=0.9, start=0.7, stars=(8, 15)),
            replace(BIG, you=1.2, reach=0.1, slowest=0.55, fastest=1.0, start=0.8, stars=(7, 13)),
            replace(BIG, you=1.15, reach=0.1, runners=5, slowest=0.65, fastest=1.0, start=0.9, gap=7.0, stars=(5, 9)),
            replace(BIG, world='nursery-tag-playground.toml', runners=6, you=1.1, reach=0.05, dizzy=1.2, safe=2.5,
                    slowest=0.7, fastest=1.0, start=1.0, gap=8.0, stars=(4, 8))),
}
# how much the runners' pace moves: per second past the gap without a catch, and at each quick catch
EASE = 0.04
HARDEN = 0.05
# a caught one is knocked away at this speed (m/s) and rolls on for this long before it spins
BOUNCE = 5.0
FLING = 0.6
# snacks: what's on the floor (only the look differs), how much of the bar one fills, how fast holding sprint empties a
# full one (a share a second), turbo's speed, how close counts as eating one (m from your middle), and how long until
# an eaten one is replaced somewhere else
SNACKS = ('berry', 'seaweed')
FILL = 0.34
DRAIN = 0.5
TURBO = 1.5
EAT = 0.5
REGROW = 2.5


def world(mode: Mode) -> Config:
    cfg = load(DEFAULT.parent / mode.world)
    if mode.snacks:
        # turbo is the world's sprint run by the bar; [sprint] seconds stay 0, so the runners still can't sprint
        assert not cfg.sprint.on, f'{mode.world} has a sprint of its own'
        cfg = replace(cfg, sprint=replace(cfg.sprint, speed=TURBO))
    return replace(cfg, colonies=replace(cfg.colonies, size=mode.runners + 1),
                   episode=replace(cfg.episode, seconds=mode.seconds),
                   tag=replace(cfg.tag, speed=mode.you, reach=mode.reach, back=mode.safe, cooldown=0.3))


class Catch(Game):
    def __init__(self, name: str, brain: Path, seed: int, keep: Path | None = None, device: str = '', level: int = 1):
        self.name, self.level, self.mode = name, level, MODES[name][level - 1]
        super().__init__(world(self.mode), brain, seed, f'kids/{name}/{level}')
        w = self.world
        assert w.tag, f'{self.mode.world} has no tag'
        self.tag = w.tag
        self.tag.it[0], self.tag.wait[0] = self.slot, 0
        # drawn again now that you're it
        self.first = replay.frame(w, 0)
        self.pace = self.mode.start
        self.catches: list[dict] = []
        self.events: list[dict] = []  # catches since the last step, for the viewer
        self.dizzy: dict[int, int] = {}
        self.last = 0  # tick of the last catch, or of the start
        self.ticks = 0
        self.began = time.time()
        self.device = device
        self.closed = False
        if self.mode.snacks and 'sprint' not in self.controls:
            self.controls.append('sprint')
        self.rng = np.random.default_rng(seed + 1)
        self.snacks: list[dict] = []
        self.coming: list[int] = [0] * self.mode.snacks  # ticks until each missing snack is put down
        self.turbo = 0.0
        self.eaten = 0
        self.boosted = 0  # ticks on turbo
        self.serial = 0
        self.grow()
        self.file = self.writer = None
        if keep:
            day = keep / time.strftime('%Y-%m-%d')
            day.mkdir(parents=True, exist_ok=True)
            self.file = day / f'{time.strftime("%H%M%S")}-{name}{level}-{seed}.jsonl.gz'
            self.header['source']['kids'] = {'mode': name, 'level': level, **dataclasses.asdict(self.mode)}
            self.writer = replay.Writer(self.file, self.header)
            self.writer.write(self.first)
            self.keep = keep

    def step(self, ticks: int, thrust: float, turn: float, yes: list[str]) -> list[dict]:
        w, frames, self.events = self.world, [], []
        self.used = time.time()
        for _ in range(ticks):
            if w.ended[0]:
                break
            actions = self.act(w).copy()
            # theirs at the pace the game has set; a caught one tumbles away from you, then spins where it stops
            actions[0, :, 0] = np.where(actions[0, :, 0] > 0, actions[0, :, 0] * self.pace, actions[0, :, 0])
            full = round(self.mode.dizzy * self.hz)
            for slot, left in self.dizzy.items():
                rolling = full - left < round(FLING * self.hz)
                actions[0, slot, 0], actions[0, slot, 1] = (1.0, 0.0) if rolling else (0.0, 1.0)
            mine = np.full(actions.shape[-1], -1.0)
            mine[0], mine[1] = np.clip(thrust, -1, 1), np.clip(turn, -1, 1)
            # a sprint is the only yes there is to say in tag; with snacks it's turbo, while the bar lasts
            boost = False
            if 'sprint' in yes and self.mode.snacks:
                boost = self.turbo > 0
                if boost:
                    w.sprinting[0, self.slot] = 1
                    self.turbo = max(0.0, self.turbo - DRAIN / self.hz)
                    self.boosted += 1
            elif 'sprint' in yes and 'sprint' in self.controls:
                mine[ACTIONS.index('sprint')] = 1.0
            actions[0, self.slot] = mine
            w.step(actions)
            self.ticks += 1
            self.munch()
            self.grow()
            self.dizzy = {s: t - 1 for s, t in self.dizzy.items() if t > 1}
            caught = int(self.tag.it[0])
            if caught != self.slot:
                self.caught(caught)
            self.adjust()
            frame = replay.frame(w, 0)
            if boost:
                me = int(w.creature_id[0, self.slot])
                for c in frame['creatures']:
                    if c['id'] == me:
                        c['sprinting'] = 1
            frames.append(frame)
            if self.writer:
                self.writer.write(frame)
        if w.ended[0]:
            self.close('over')
        return frames

    def caught(self, slot: int):
        w, hz, tag = self.world, self.hz, self.tag
        tag.it[0], tag.back[0], tag.since[0] = self.slot, slot, 0
        tag.wait[0] = round(w.cfg.tag.cooldown * hz)
        self.dizzy[slot] = round(self.mode.dizzy * hz)
        # boing: knocked away from you, facing away
        away = w.pos[0, slot] - w.pos[0, self.slot]
        w.heading[0, slot] = np.arctan2(away[1], away[0])
        body = w.physics.bodies[0][slot]
        body.velocity = tuple(float(v) for v in BOUNCE * away / max(np.hypot(*away), 1e-6))
        w.physics.read()
        took = (self.ticks - self.last) / hz
        # quick catches: they're too easy to get
        if took < self.mode.gap / 2:
            self.pace = min(self.mode.fastest, self.pace + HARDEN)
        self.last = self.ticks
        x, y = w.pos[0, slot]
        event = {'at': round(self.ticks / hz, 2), 'tick': int(w.tick), 'id': int(w.creature_id[0, slot]),
                 'x': round(float(x), 2), 'y': round(float(y), 2), 'took': round(took, 2), 'pace': round(self.pace, 3)}
        self.catches.append(event)
        self.events.append(event)

    def munch(self):
        x, y = self.world.pos[0, self.slot]
        for s in [s for s in self.snacks if np.hypot(s['x'] - x, s['y'] - y) < EAT]:
            self.snacks.remove(s)
            self.coming.append(round(REGROW * self.hz))
            self.turbo = min(1.0, self.turbo + FILL)
            self.eaten += 1

    def grow(self):
        left = []
        for t in self.coming:
            t -= 1
            if t <= 0 and (spot := self.spot()):
                self.serial += 1
                self.snacks.append({'id': self.serial, 'x': spot[0], 'y': spot[1],
                                    'kind': SNACKS[int(self.rng.integers(len(SNACKS)))]})
            else:
                # nowhere clear this time: try again next tick
                left.append(max(t, 1))
        self.coming = left

    def spot(self) -> tuple[float, float] | None:
        # somewhere clear: off the walls and blocks, not under you, not on another snack
        w = self.world
        half = w.cfg.arena.size / 2 - 0.8
        for _ in range(50):
            x, y = (float(v) for v in self.rng.uniform(-half, half, 2))
            if any(np.hypot(x - b.x, y - b.y) < max(b.w, b.h) / 2 + 0.6 for b in w.cfg.block):
                continue
            if np.hypot(*(w.pos[0, self.slot] - (x, y))) < 2.0:
                continue
            if any(np.hypot(x - s['x'], y - s['y']) < 1.5 for s in self.snacks):
                continue
            return round(x, 2), round(y, 2)
        return None

    def adjust(self):
        # a second at a time, past the gap without a catch: slower runners
        waited = (self.ticks - self.last) / self.hz
        if waited > self.mode.gap and self.ticks % self.hz == 0:
            self.pace = max(self.mode.slowest, self.pace - EASE)

    def score(self) -> dict:
        w = self.world
        return {'catches': len(self.catches), 'seconds': round(self.ticks / self.hz, 1),
                'length': self.mode.seconds, 'over': bool(w.ended[0]), 'pace': round(self.pace, 3),
                'level': self.level, 'stars': list(self.mode.stars),
                'snacks': self.snacks if self.mode.snacks else [], 'turbo': round(self.turbo, 3),
                'dizzy': [int(w.creature_id[0, s]) for s in self.dizzy]}

    def close(self, why: str):
        """The game's line in plays.jsonl, once: why it stopped (over, quit, new game, idle) and how it went."""
        if self.closed:
            return
        self.closed = True
        played = self.ticks / self.hz
        when = datetime.fromtimestamp(self.began).astimezone().isoformat(timespec='seconds')
        line = {'when': when, 'mode': self.name,
                'level': self.level, 'why': why, 'played': round(played, 1), 'length': self.mode.seconds, 'catches': len(self.catches),
                'per_minute': round(60 * len(self.catches) / played, 2) if played else 0.0,
                'pace': round(self.pace, 3), 'device': self.device, 'brain': self.header['source']['brain'],
                'seed': self.header['source']['seed'], 'replay': self.file.name if self.file else None,
                'times': [c['at'] for c in self.catches], 'paces': [c['pace'] for c in self.catches],
                'snacks': self.eaten, 'turbo': round(self.boosted / self.hz, 1)}
        if self.writer:
            self.writer.close()
            with open(self.keep / 'plays.jsonl', 'a') as f:
                f.write(json.dumps(line) + '\n')
        log.info('game ended', mode=self.name, why=why, played=line['played'], catches=line['catches'],
                 pace=line['pace'])
