# What pays for what, before a rung runs: every reward source a world and a training recipe switch on, when it pays,
# who gets it, how big it is and how far behind the choice that earns it, set against how far ahead the discount looks.
#
#   uv run python -m terrarium.ledger WORLD.toml TRAIN.toml [--json]
#
# The sources are a registry below, written by hand from Forage.step. One that pays in the step and isn't in the
# registry is printed as UNCOVERED, never left out.

import argparse
import dataclasses
import inspect
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import forage
from .config import Config, Reward, Train, load, load_train

SEEN = (10, 30, 60)

# world hooks whose name in the step isn't their config section's
SECTION = {'flags': 'flag'}


@dataclass
class Row:
    source: str
    when: str
    kind: str       # event, per-second, potential or terminal
    who: str
    size: str
    delay: str
    ref: str


@dataclass
class Source:
    key: str            # 'reward.stored' or 'game.tree'
    kind: str
    when: str
    anchor: str         # text in forage.py where it pays
    on: Callable[[Config, Reward], bool]
    size: Callable[[Config, Reward], str]
    who: str = 'own'    # own: the nim's own, through the colony blend; else a sentence
    delay: Callable[[Config, Reward], tuple[float, str] | None] = lambda c, r: None


def meal(c: Config, e: float) -> float:
    """What a food eaten at energy e is worth in hunger squared, per unit of `needs`."""
    kept = min(c.energy.food, 1 - e)
    return kept * (2 * (1 - e - kept) + kept)


def starve(c: Config) -> list[tuple[float, str]]:
    out = []
    if c.energy.drain > 0:
        out.append((c.energy.start / c.energy.drain, 'starving'))
    if c.night.on and c.night.cold > 0:
        out.append((c.night.length, "a night's cold"))
    if c.water.on and c.water.drain > 0:
        out.append((c.water.start / c.water.drain, 'thirst'))
    return out


def death_delay(c: Config, r: Reward) -> tuple[float, str] | None:
    got = starve(c)
    if not got:
        return None
    return max(s for s, _ in got), ', '.join(f'{what} {s:g} s' for s, what in got)


def tree_when(c: Config) -> str:
    return 'an apple unloaded in the nest' if c.tree.home else 'an apple eaten'


REGISTRY = [
    Source('reward.food', 'event', 'a food eaten, by its energy', 'r.food * gain',
           lambda c, r: r.food != 0, lambda c, r: f'{r.food:g} a food ({c.energy.food:g} energy)'),
    Source('reward.stored', 'event', 'a food unloaded in the nest', 'r.stored * (w.stored',
           lambda c, r: r.stored != 0, lambda c, r: f'{r.stored:g} a food'),
    Source('reward.jelly', 'event', 'a food of the store eaten', 'r.jelly * (w.jelly',
           lambda c, r: r.jelly != 0, lambda c, r: f'{r.jelly:g} a unit eaten'),
    Source('reward.hatch', 'event', "an egg hatching in the nim's colony", 'r.hatch * (w.hatched',
           lambda c, r: r.hatch != 0, lambda c, r: f'{r.hatch:g} an egg, to each living member',
           delay=lambda c, r: (c.hatch.seconds, 'egg to hatch') if c.hatch.cost > 0 and c.hatch.seconds > 0 else None),
    Source('reward.death', 'terminal', 'the nim dying', 'r.death * (alive',
           lambda c, r: r.death != 0, lambda c, r: f'{r.death:g} once', delay=death_delay),
    Source('reward.alive', 'per-second', 'every second alive', 'r.alive * lived',
           lambda c, r: r.alive != 0, lambda c, r: f'{r.alive:g} a second'),
    Source('reward.effort', 'per-second', 'energy spent, drain included', 'r.effort * (w.spent',
           lambda c, r: r.effort != 0,
           lambda c, r: f'-{r.effort:g} per {c.energy.food:g} energy ({r.effort * c.energy.drain / c.energy.food:g} a second at rest)'),
    Source('reward.snug', 'per-second', 'warmth: in its nest, or with mates close', 'r.snug + r.warm',
           lambda c, r: r.snug != 0, lambda c, r: f'{r.snug:g} a second at full warmth'),
    Source('reward.warm', 'per-second', 'warmth in the dark, times how dark', 'r.snug + r.warm',
           lambda c, r: r.warm != 0, lambda c, r: f'{r.warm:g} a second at full warmth and dark'),
    Source('reward.dawn', 'event', 'dawn, for a nim in its own nest', 'r.dawn * dawned',
           lambda c, r: r.dawn != 0, lambda c, r: f'{r.dawn:g} a nim at each dawn',
           delay=lambda c, r: (c.night.length + c.night.dusk, "the night's length") if c.night.on else None),
    Source('reward.novelty', 'event', 'a block moved or a new thing done (terrarium/fun.py)', 'self.fun',
           lambda c, r: r.novelty != 0, lambda c, r: f'scaled by {r.novelty:g}'),
    Source('reward.variety', 'event', 'a different thing done (terrarium/fun.py)', 'self.fun',
           lambda c, r: r.variety != 0, lambda c, r: f'scaled by {r.variety:g}'),
    Source('reward.needs', 'event', 'a meal or a drink: hunger (thirst) squared, before less after', 'r.needs * kept',
           lambda c, r: r.needs != 0,
           lambda c, r: (f'{r.needs:g} x (hunger² before - after): a food at energy 0.5 {r.needs * meal(c, 0.5):.2f}, '
                         f'at 0.9 {r.needs * meal(c, 0.9):.2f}')),
    Source('reward.needs_lost', 'per-second', 'what the drain, the cold and effort take, as the same square', 'r.needs_lost * lost',
           lambda c, r: r.needs_lost != 0,
           lambda c, r: (f'-{r.needs_lost:g} x the fall in hunger²: at energy 0.5, '
                         f'-{r.needs_lost * c.energy.drain:.4f} a second from the drain'
                         + (f', -{r.needs_lost * c.night.cold:.4f} more in full dark' if c.night.on and c.night.cold else ''))),
    Source('reward.hunger', 'per-second', 'every second, by how hungry (and thirsty)', 'r.hunger * w.cfg.dt',
           lambda c, r: r.hunger != 0, lambda c, r: f'-{r.hunger:g} x (1-e)² a second: {r.hunger * 0.25:g} at energy 0.5'),
    Source('reward.home', 'potential', 'carrying food nearer the nest: the change in what the crop is worth there', 'carried_worth(w, r)',
           lambda c, r: r.home != 0,
           lambda c, r: (f'{r.home:g} x food carried x (1 - distance / {c.arena.size:g}): a food {r.home * 10 / c.arena.size:.3f} '
                         f'for each 10 m nearer; nets 0 over a round trip')),
    Source('game.tree', 'event', '', 'w.tree.points', lambda c, r: c.tree.on,
           lambda c, r: f'{c.tree.points:g} an apple' + (f', -{c.tree.hop:g} a jump' if c.tree.hop else ''),
           who='every living nim of the colony that carried it, in full (the colony blend leaves equal pay as it is)'),
    Source('game.tag', 'per-second', 'every second: it pays, the rest gain', 'w.tag.points', lambda c, r: c.tag.on,
           lambda c, r: f'{c.tag.points:g} a second: it -{c.tag.points:g}, the others +{c.tag.points:g} / (alive - 1) each',
           who='the one that is it pays; the rest of the arena share it'),
    Source('game.seek', 'per-second', 'every second after the hiders hide: seeker sees a hider or not', 'w.seek.points',
           lambda c, r: c.seek.on, lambda c, r: f'{c.seek.points:g} a second, seekers up when a hider is seen, hiders down',
           who='seekers and hiders, opposite signs'),
    Source('game.flags', 'event', 'a flag picked up, brought home, and carried nearer its nest', 'w.flags.points',
           lambda c, r: c.flag.on,
           lambda c, r: (f'{c.flag.points:g} a capture, {c.flag.points * c.flag.pickup:g} a pickup '
                         f'(-{c.flag.points * c.flag.pickup * c.flag.charge:g} to the other side), {c.flag.home:g} a metre nearer'),
           who="the capturing colony's members; the other side pays the same"),
    Source('game.peek', 'event', 'a hidden berry found', 'w.peek.points', lambda c, r: c.peek.on,
           lambda c, r: f'{c.peek.points:g} a berry', who='every living nim in the arena, in full'),
    Source('game.dung', 'event', 'a dropping put down on the midden', 'w.dung.points', lambda c, r: c.dung.on,
           lambda c, r: f'{c.dung.points:g} a dropping', who="every living member of the dropper's colony"),
]

DEFAULT_WHEN = {'game.tree': tree_when}

WHEN = {'event': 'at the event', 'per-second': 'each second', 'potential': 'each step, as the crop gets nearer',
        'terminal': 'at the end'}


def line_of(anchor: str) -> int | None:
    lines = inspect.getsource(forage).splitlines()
    return next((i + 1 for i, text in enumerate(lines) if anchor in text), None)


def blend(c: Config, r: Reward) -> str:
    n = c.colonies.size
    own = 1 - r.colony + r.colony / n
    return f'colony {r.colony:g}, n {n}: own share {own:.3g}, each mate {r.colony / n:.3g}'


def horizon(c: Config, train: Train) -> dict:
    p = train.ppo
    step = c.dt * p.repeat
    efold = lambda g: -step / math.log(g) if 0 < g < 1 else math.inf
    return {
        'step_s': step, 'gamma': p.gamma, 'lam': p.lam, 'efold_s': efold(p.gamma),
        'weights': {s: p.gamma ** (s / step) for s in SEEN},
        'gae_efold_s': efold(p.gamma * p.lam), 'rollout_s': p.steps * step, 'episode_s': c.episode.seconds,
    }


def timing(c: Config, train: Train) -> dict:
    n, e = c.night, c.episode.seconds
    if not n.on:
        return {'night': False, 'episode_s': e}
    dark = n.cycle - n.length
    free = train.start.staggered
    return {
        'night': True, 'cycle_s': n.cycle, 'length_s': n.length, 'dusk_s': n.dusk, 'episode_s': e,
        'first_dusk_s': dark - n.dusk, 'first_dark_s': dark, 'first_dawn_s': n.cycle,
        'staggered': free, 'start_dark': n.start_dark,
        'dark_reached': free or n.start_dark > 0 or e > dark,
        'dawn_reached': free or n.start_dark > 0 or e > n.cycle,
    }


def rows(c: Config, r: Reward, h: dict) -> list[Row]:
    out = []
    for s in REGISTRY:
        if not s.on(c, r):
            continue
        line = line_of(s.anchor)
        when = s.when or DEFAULT_WHEN[s.key](c)
        delay = WHEN[s.kind]
        got = s.delay(c, r)
        if got:
            sec, what = got
            delay += f'; payoff sits {sec:g} s on ({what}), weight {h['gamma'] ** (sec / h['step_s']):.2f}'
        who = blend(c, r) if s.who == 'own' else s.who
        out.append(Row(s.key, when, s.kind, who, s.size(c, r), delay, f'forage.py:{line}' if line else 'forage.py'))
    return out


def uncovered(r: Reward, c: Config, source: str | None = None) -> list[str]:
    source = source if source is not None else inspect.getsource(forage.Forage.step)
    known = {s.key for s in REGISTRY}
    out = []
    for field in dataclasses.fields(r):
        if field.name != 'colony' and getattr(r, field.name) != 0 and f'reward.{field.name}' not in known:
            out.append(f'reward.{field.name} = {getattr(r, field.name):g}')
    hooks = {k.removeprefix('game.') for k in known if k.startswith('game.')}
    for name in dict.fromkeys(re.findall(r'play \+= w\.(\w+)\.points', source)):
        section = getattr(c, SECTION.get(name) or name, None)
        if name not in hooks and (section is None or getattr(section, 'on', True)):
            out.append(f'game hook w.{name} pays through play')
    return out


def deaths_possible(c: Config) -> bool:
    return bool(starve(c))


def warnings(c: Config, train: Train, hz: dict, tm: dict) -> list[tuple[str, str]]:
    r, out = train.reward, []
    step, efold = hz['step_s'], hz['efold_s']
    on = lambda key: any(s.key == key and s.on(c, r) for s in REGISTRY)

    if tm['night']:
        if not tm['dark_reached']:
            out.append(('never-dark', f"dark falls at {tm['first_dark_s']:g} s of the day and games last {tm['episode_s']:g} s, "
                        'so no training game sees a night (set [start] staggered, [night] start_dark, or a longer episode)'))
        elif not tm['dawn_reached']:
            out.append(('never-dawn', f"dark falls at {tm['first_dark_s']:g} s but dawn at {tm['first_dawn_s']:g} s is after "
                        f"the {tm['episode_s']:g} s game ends, so no game sees a night end"))
        if r.dawn != 0 and not tm['dawn_reached']:
            out.append(('never-dawn', f"reward.dawn = {r.dawn:g} but no training game reaches dawn ({tm['first_dawn_s']:g} s)"))

    if r.stored != 0 and c.tree.on and c.tree.home:
        out.append(('double-pay', f'{"an apple" if c.tree.apples else "a food"} unloaded in the nest is paid by reward.stored ({r.stored:g}) and by [tree] points '
                    f'({c.tree.points:g} an apple, to every living nim of the colony): twice'))
    if r.food != 0 and c.tree.on and not c.tree.home:
        out.append(('double-pay', f'an apple eaten is paid by reward.food ({r.food:g}) and by [tree] points ({c.tree.points:g})'))
    if r.needs != 0 and (r.food != 0 or r.jelly != 0):
        who = '/'.join(k for k, v in (('food', r.food), ('jelly', r.jelly)) if v)
        out.append(('double-pay', f'a meal is paid by reward.needs ({r.needs:g}, the hunger it ends) and by reward.{who}'))

    paid = []
    if r.stored == 0 and c.tree.on and c.tree.home:
        paid.append('delivery (food unloaded in the nest) is paid by [tree] points, though reward.stored = 0')
    if r.food == 0 and r.needs != 0:
        paid.append('eating is paid by reward.needs, though reward.food = 0')
    if r.food == 0 and c.tree.on and not c.tree.home:
        paid.append('taking an apple is paid by [tree] points, though reward.food = 0')
    if r.jelly == 0 and r.needs != 0:
        paid.append("eating the store's jelly is paid by reward.needs (a store's jelly counts), though reward.jelly = 0")
    if r.alive == 0 and r.needs_lost != 0:
        paid.append('staying alive is charged by reward.needs_lost (drain and cold as they are felt), though reward.alive = 0')
    for text in paid:
        out.append(('paid-elsewhere', text))

    if math.isfinite(efold):
        for row in REGISTRY:
            if not row.on(c, r):
                continue
            got = row.delay(c, r)
            if got and got[0] > 2 * efold:
                dense = ' (reward.needs_lost charges the fall as it happens)' if row.key == 'reward.death' and (r.needs_lost or r.hunger) else ''
                out.append(('delay', f'{row.key}: the payoff sits {got[0]:g} s on ({got[1]}), {got[0] / efold:.1f} e-folds '
                            f'of the discount ({efold:.1f} s), weight {math.exp(-got[0] / efold):.2f}{dense}'))

    if r.death >= 0 and deaths_possible(c):
        out.append(('death-zero', f'reward.death = {r.death:g} but games have deaths ({", ".join(w for _, w in starve(c))}): dying costs nothing'))
    if r.needs != r.needs_lost:
        out.append(('turnover', f'reward.needs ({r.needs:g}) and reward.needs_lost ({r.needs_lost:g}) differ: eating and burning '
                    f'the same energy again nets {r.needs - r.needs_lost:+g} a round'))

    for text in uncovered(r, c):
        out.append(('uncovered', f'UNCOVERED: {text}, not in the ledger registry'))
    return out


def build(c: Config, train: Train) -> dict:
    hz, tm = horizon(c, train), timing(c, train)
    return {'rows': [dataclasses.asdict(x) for x in rows(c, train.reward, hz)], 'horizon': hz, 'timing': tm,
            'blend': blend(c, train.reward), 'warnings': [{'code': k, 'text': t} for k, t in warnings(c, train, hz, tm)]}


def render(data: dict, names: tuple[str, str]) -> str:
    hz, tm = data['horizon'], data['timing']
    out = [f'# Payoff ledger: {names[0]} with {names[1]}', '', '## Sources', '',
           '| source | when it pays | who gets it | size | delay / weight |', '|---|---|---|---|---|']
    for x in data['rows']:
        out.append(f"| `{x['source']}` ({x['ref']}) | {x['when']} ({x['kind']}) | {x['who']} | {x['size']} | {x['delay']} |")
    out += ['', f"Colony blend: {data['blend']}.", '', '## Horizon', '']
    out += [f"- decision step {hz['step_s']:g} s, gamma {hz['gamma']:g}: e-fold {hz['efold_s']:.1f} s; "
            f"weight at {', '.join(f'{s} s {w:.2f}' for s, w in hz['weights'].items())}",
            f"- GAE (gamma x lambda {hz['gamma'] * hz['lam']:.4g}): e-fold {hz['gae_efold_s']:.1f} s",
            f"- rollout {hz['rollout_s']:.1f} s, training episode {hz['episode_s']:g} s"]
    out += ['', '## Timing', '']
    if tm['night']:
        out.append(f"- night: cycle {tm['cycle_s']:g} s, night {tm['length_s']:g} s, dusk {tm['dusk_s']:g} s; "
                   f"first dusk {tm['first_dusk_s']:g} s, dark {tm['first_dark_s']:g} s, dawn {tm['first_dawn_s']:g} s, "
                   f"episode {tm['episode_s']:g} s")
        out.append(f"- staggered starts {'on' if tm['staggered'] else 'off'}, start_dark {tm['start_dark']:g}; "
                   f"dark reached in training: {'yes' if tm['dark_reached'] else 'no'}, dawn: {'yes' if tm['dawn_reached'] else 'no'}")
    else:
        out.append(f"- no nights; episode {tm['episode_s']:g} s")
    out += ['', '## Warnings', '']
    out += [f"{i}. [{w['code']}] {w['text']}" for i, w in enumerate(data['warnings'], 1)] or ['None.']
    return '\n'.join(out) + '\n'


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description='what pays for what in a world and a training recipe')
    p.add_argument('world')
    p.add_argument('train')
    p.add_argument('--json', action='store_true')
    a = p.parse_args(argv)
    data = build(load(a.world), load_train(a.train))
    sys.stdout.write(json.dumps(data, indent=2) + '\n' if a.json else render(data, (Path(a.world).name, Path(a.train).name)))


if __name__ == '__main__':
    main()
