# World and training config, read from TOML files. There are no defaults here on
# purpose: every number lives in a file, so a run record's copy is the whole story.

import dataclasses
import tomllib
import typing
from dataclasses import dataclass
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / 'configs' / 'world.toml'
TRAIN = DEFAULT.parent / 'train.toml'


@dataclass(frozen=True)
class Arena:
    size: float
    scatter: float
    maze: int       # rooms a side of a maze its blocks make anew each episode (0: no maze)


@dataclass(frozen=True)
class Creature:
    radius: float
    mass: float
    max_speed: float
    reverse: float
    turn_rate: float
    accel: float
    friction: float


@dataclass(frozen=True)
class Energy:
    start: float
    drain: float
    move: float
    turn: float
    food: float


@dataclass(frozen=True)
class Colonies:
    count: int
    size: int
    # places each colony has beyond the ones it starts with, empty until it hatches into them
    room: int
    nest_radius: float
    nest_distance: float
    spawn_ring: float

    @property
    def slots(self) -> int:
        return self.size + self.room


@dataclass(frozen=True)
class Food:
    count: int
    radius: float
    regrow_min: float
    regrow_max: float
    clearance: float
    patches: int
    patch_radius: float
    middle: int


@dataclass(frozen=True)
class Crop:
    capacity: int
    slow: float
    start: int


@dataclass(frozen=True)
class Jelly:
    energy: float
    hunger: float


@dataclass(frozen=True)
class Hatch:
    cost: int
    threshold: int
    seconds: float

    @property
    def on(self) -> bool:
        return self.cost > 0


@dataclass(frozen=True)
class Young:
    seconds: float
    speed: float
    energy: float
    start: bool     # the Terrikins an episode starts with are young too, not only hatchlings

    @property
    def on(self) -> bool:
        return self.seconds > 0


@dataclass(frozen=True)
class Night:
    cycle: float
    length: float
    dusk: float
    cold: float
    nest: float
    huddle: float
    reach: float

    @property
    def on(self) -> bool:
        return self.cycle > 0 and self.length > 0


@dataclass(frozen=True)
class Tired:
    drain: float
    rest: float
    still: float
    below: float
    slowest: float

    @property
    def on(self) -> bool:
        return self.drain > 0


@dataclass(frozen=True)
class Sprint:
    speed: float
    seconds: float
    cooldown: float
    energy: float

    @property
    def on(self) -> bool:
        return self.seconds > 0 and self.speed > 1


@dataclass(frozen=True)
class Flowers:
    count: int
    every_min: float
    every_max: float
    open: float
    radius: float
    food: int
    boost: float
    speed: float
    spots: int
    spot_gap: float

    @property
    def on(self) -> bool:
        return self.count > 0


@dataclass(frozen=True)
class Grab:
    reach: float
    grip: float
    seconds: float
    energy: float

    @property
    def on(self) -> bool:
        return self.grip > 0


@dataclass(frozen=True)
class Carry:
    reach: float
    slow: float
    energy: float

    @property
    def on(self) -> bool:
        return self.reach > 0


@dataclass(frozen=True)
class Smell:
    cell: float
    spread: float
    fade: float
    leak: float

    @property
    def on(self) -> bool:
        return self.spread > 0


@dataclass(frozen=True)
class Hearing:
    range: float

    @property
    def on(self) -> bool:
        return self.range > 0


@dataclass(frozen=True)
class Ground:
    friction: float


@dataclass(frozen=True)
class Block:
    x: float
    y: float
    angle: float
    w: float
    h: float
    mass: float
    friction: float
    # small enough to pick up and carry (with [carry] on), as a berry is
    carry: bool
    # seconds after a carried block is put down that it goes back where it started, once that's clear (a door that
    # swings shut); 0: it stays where it's put
    shut: float


@dataclass(frozen=True)
class Tag:
    reach: float
    cooldown: float
    points: float
    speed: float    # it runs at this share of top speed (more than 1 gives the chaser a chance in the open)
    back: float     # seconds before the new it can tag the one who tagged it (negative: never)

    @property
    def on(self) -> bool:
        return self.reach > 0


@dataclass(frozen=True)
class Seek:
    prep: float
    points: float

    @property
    def on(self) -> bool:
        return self.prep > 0


@dataclass(frozen=True)
class Flag:
    points: float
    pickup: float
    charge: float   # share of a pickup's points taken off the other side
    home: float     # points a metre a carrier brings the other side's flag nearer its own nest
    steal: bool     # a touch takes the flag off its carrier, rather than sending it home
    guard: float    # seconds a new carrier can't be robbed
    lie: float      # seconds a flag that's been put down waits before going home

    @property
    def on(self) -> bool:
        return self.points > 0


@dataclass(frozen=True)
class Peek:
    show: float      # seconds the berry is in sight
    points: float
    gap: float       # seconds from one found to the next turning up
    timeout: float   # seconds after hiding that it moves if nobody found it
    near: float      # it turns up between these distances in front of someone
    far: float
    spin: bool       # turn everyone round at random when it hides
    again: float     # once hidden, it's back in sight for `flash` s every `again` s at the same spot (0 is never)
    flash: float

    @property
    def on(self) -> bool:
        return self.show > 0


@dataclass(frozen=True)
class Vision:
    rays: int
    fov: float
    range: float
    cover: float
    spread: float
    side: float


@dataclass(frozen=True)
class Episode:
    seconds: float


@dataclass(frozen=True)
class Config:
    tick_hz: int
    substeps: int
    slop: float
    arena: Arena
    creature: Creature
    energy: Energy
    colonies: Colonies
    food: Food
    crop: Crop
    jelly: Jelly
    hatch: Hatch
    young: Young
    night: Night
    sprint: Sprint
    tired: Tired
    flowers: Flowers
    grab: Grab
    carry: Carry
    smell: Smell
    hearing: Hearing
    tag: Tag
    seek: Seek
    flag: Flag
    peek: Peek
    ground: Ground
    vision: Vision
    episode: Episode
    block: tuple[Block, ...]

    @property
    def dt(self) -> float:
        return 1 / self.tick_hz

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Reward:
    food: float
    death: float
    alive: float
    stored: float
    jelly: float
    colony: float
    home: float
    snug: float
    warm: float
    effort: float
    hatch: float
    novelty: float
    variety: float


@dataclass(frozen=True)
class PPO:
    samples: int
    repeat: int
    arenas: int
    steps: int
    epochs: int
    minibatches: int
    lr: float
    anneal: bool
    warmup: int
    gamma: float
    bootstrap: bool
    lam: float
    clip: float
    entropy: float
    coins: float
    coins_for: tuple[str, ...]
    side: float
    side_back: int
    closure: float
    value: float
    max_grad_norm: float
    kl_stop: float
    give_up: int
    stuck: int
    stuck_seconds: float
    checkpoint_every: int


@dataclass(frozen=True)
class Start:
    fresh: tuple[str, ...]
    staggered: bool
    spread: bool


@dataclass(frozen=True)
class Train:
    reward: Reward
    ppo: PPO
    start: Start

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class ConfigError(ValueError):
    pass


def build(cls, data, where='config'):
    """Turn parsed TOML into the dataclass, refusing missing, unknown or mistyped keys."""
    if not isinstance(data, dict):
        raise ConfigError(f'{where}: expected a table, got {type(data).__name__}')
    hints = typing.get_type_hints(cls)
    names = {f.name for f in dataclasses.fields(cls)}
    if unknown := sorted(set(data) - names):
        raise ConfigError(f'{where}: unknown key(s) {", ".join(unknown)}')
    if missing := sorted(names - set(data)):
        raise ConfigError(f'{where}: missing key(s) {", ".join(missing)}')
    return cls(**{name: convert(hints[name], data[name], f'{where}.{name}') for name in names})


def convert(kind, value, where):
    if dataclasses.is_dataclass(kind):
        return build(kind, value, where)
    if typing.get_origin(kind) is tuple:
        item = typing.get_args(kind)[0]
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f'{where}: expected a list of tables')
        return tuple(convert(item, v, f'{where}[{i}]') for i, v in enumerate(value))
    if kind is bool:
        if not isinstance(value, bool):
            raise ConfigError(f'{where}: expected true or false, got {value!r}')
        return value
    # TOML ints are fine where a float is wanted, but not the other way round, and never bools
    if isinstance(value, bool) or not (isinstance(value, kind) or (kind is float and isinstance(value, int))):
        raise ConfigError(f'{where}: expected {kind.__name__}, got {value!r}')
    return kind(value)


# keys added after worlds were first recorded, as they were before: off. Only for reading old run
# records (serve.py), never for configs on disk, which have every key
SINCE = {'arena': {'scatter': 0.0, 'maze': 0},
         'colonies': {'room': 0},
         'vision': {'cover': 0.0, 'spread': 1.0, 'side': 1.0},
         'night': {'cycle': 0.0, 'length': 0.0, 'dusk': 0.0, 'cold': 0.0, 'nest': 0.0, 'huddle': 0.0, 'reach': 0.0},
         'energy': {'turn': 0.0},
         'hatch': {'cost': 0, 'threshold': 0, 'seconds': 0.0},
         'young': {'seconds': 0.0, 'speed': 1.0, 'energy': 1.0, 'start': False},
         'tag': {'reach': 0.0, 'cooldown': 0.0, 'points': 0.0, 'speed': 1.0, 'back': -1.0},
         'seek': {'prep': 0.0, 'points': 0.0},
         'flag': {'points': 0.0, 'pickup': 0.0, 'charge': 1.0, 'home': 0.0, 'steal': False, 'guard': 0.0, 'lie': 0.0},
         'peek': {'show': 0.0, 'points': 0.0, 'gap': 0.0, 'timeout': 0.0, 'near': 0.0, 'far': 0.0, 'spin': False, 'again': 0.0, 'flash': 0.0},
         'sprint': {'speed': 1.0, 'seconds': 0.0, 'cooldown': 0.0, 'energy': 0.0},
         'tired': {'drain': 0.0, 'rest': 0.0, 'still': 0.0, 'below': 0.0, 'slowest': 1.0},
         'food': {'middle': 0},
         'flowers': {'count': 0, 'every_min': 0.0, 'every_max': 0.0, 'open': 0.0, 'radius': 0.0, 'food': 0, 'boost': 0.0,
                     'speed': 1.0, 'spots': 0, 'spot_gap': 0.0},
         'grab': {'reach': 0.0, 'grip': 0.0, 'seconds': 0.0, 'energy': 0.0},
         'carry': {'reach': 0.0, 'slow': 0.0, 'energy': 0.0},
         'smell': {'cell': 0.0, 'spread': 0.0, 'fade': 0.0, 'leak': 0.0},
         'hearing': {'range': 0.0}}


def upgrade(data: dict) -> dict:
    """A recorded world config with the keys it predates filled in, so the world it describes is unchanged."""
    out = {**data, **{k: {**old, **data.get(k, {})} for k, old in SINCE.items()}}
    if 'block' in data:
        # the vault's hinged doors were taken out again (0.3): those worlds come back with doors that slide
        out['block'] = [{'carry': False, 'shut': 0.0} | {k: v for k, v in b.items() if k != 'hinge'} for b in data['block']]
    return out


def load(path: Path | str = DEFAULT) -> Config:
    with open(path, 'rb') as f:
        return build(Config, tomllib.load(f))


def load_train(path: Path | str = TRAIN) -> Train:
    with open(path, 'rb') as f:
        return build(Train, tomllib.load(f), 'train')
