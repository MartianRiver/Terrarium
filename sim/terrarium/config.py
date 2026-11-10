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
    # what the body does changes what staying alive costs; all of these are off at their defaults
    # share of `drain` paid while still (thrust below [tired] still if tired is on, else below `still`)
    rest: float = 1.0
    # share of `drain` paid instead while still in the dark and warm (see Night.nest and Night.huddle)
    sleep: float = 1.0
    still: float = 0.1
    # energy a second per kg of body, fat and load, at full speed (0: moving costs only thrust and turn)
    work: float = 0.0

    def __post_init__(self):
        if min(self.rest, self.sleep, self.still, self.work) < 0:
            raise ConfigError('[energy] rest, sleep, still and work are 0 or more')


@dataclass(frozen=True)
class Fat:
    capacity: float = 0.0   # a reserve beside energy, up to this much (0: no fat)
    keep: float = 0.8       # share of the food past a full bar that is kept as fat
    below: float = 0.5      # fat turns back into energy while energy is below this...
    rate: float = 0.02      # ...at up to this much a second
    heavy: float = 0.0      # kg each unit of fat weighs, for what moving costs ([energy] work)

    def __post_init__(self):
        if self.capacity < 0 or self.rate < 0 or self.heavy < 0:
            raise ConfigError('[fat] capacity, rate and heavy are 0 or more')
        if not 0 < self.keep <= 1:
            raise ConfigError('[fat] keep is a share, above 0 to 1')
        if not 0 <= self.below <= 1:
            raise ConfigError('[fat] below is an energy, 0 to 1')

    @property
    def on(self) -> bool:
        return self.capacity > 0


@dataclass(frozen=True)
class Colonies:
    count: int
    size: int
    # places each colony has beyond the ones it starts with, empty until it hatches into them
    room: int
    nest_radius: float
    nest_distance: float
    spawn_ring: float
    # m² of nest a place needs: the nest grows to hold the colony (size + room) if that's more than nest_radius (0: off)
    nest_area: float = 0.0

    @property
    def slots(self) -> int:
        return self.size + self.room


@dataclass(frozen=True)
class Home:
    near: float      # the way home is felt in full within this far (m) of the nest's centre
    far: float       # and fades to nothing by here (0: felt everywhere)
    compass: bool    # which way it faces in the world (off: compass_sin and compass_cos read 0)


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
    # kg each thing carried weighs (food in the crop, a berry or dropping in the jaws), for what moving costs
    mass: float = 0.0


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
    start: bool     # the nims an episode starts with are young too, not only hatchlings

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
    start_dark: float   # share of games that start at nightfall, not at the start of the day
    chill_time: float   # seconds a nim's felt chill takes to follow the cold it's in

    def __post_init__(self):
        if self.chill_time <= 0:
            raise ConfigError('[night] chill_time is seconds, above 0')
        if not 0 <= self.start_dark <= 1:
            raise ConfigError('[night] start_dark is a share, 0 to 1')
        if self.start_dark > 0 and not (self.cycle > 0 and self.length > 0):
            raise ConfigError('[night] start_dark needs nights on ([night] cycle and length above 0)')

    @property
    def on(self) -> bool:
        return self.cycle > 0 and self.length > 0


@dataclass(frozen=True)
class Water:
    ponds: int          # ponds in a game (0: no thirst)
    radius: float
    distance: float     # from colony 0's nest centre to a pond's centre
    drain: float        # water lost a second
    drink: float        # water gained a second with its centre in a pond
    still: float        # drinking slows with speed: all of `drink` at a stop, none at this speed (0: speed doesn't matter)
    start: float

    def __post_init__(self):
        if self.ponds < 0:
            raise ConfigError('[water] ponds is a count, 0 or more')
        if self.drain < 0 or self.drink < 0:
            raise ConfigError('[water] drain and drink are per second, 0 or more')
        if self.still < 0:
            raise ConfigError('[water] still is a speed, 0 or more')
        if not 0 <= self.start <= 1:
            raise ConfigError('[water] start is a share, 0 to 1')
        if self.ponds and (self.radius <= 0 or self.distance < 0):
            raise ConfigError('[water] radius is above 0 and distance 0 or more')

    @property
    def on(self) -> bool:
        return self.ponds > 0


@dataclass(frozen=True)
class Grass:
    cell: float         # grid cell size, m
    meadows: int        # meadows in a game (0: no grass)
    radius: float
    distance: float     # from colony 0's nest centre to a meadow's centre
    base: float         # cover outside the meadows, 0 to 1
    regrow: float       # cover a cell regains a second, up to its own starting cover
    bite: float         # cover a nim removes a second from the cell it stands on, while its energy is below 1
    still: float        # grazing slows with speed: all of `bite` at a stop, none at this speed (0: speed doesn't matter)
    food: float         # energy per unit of cover eaten (a full cell gives this much, whatever its size)

    def __post_init__(self):
        if self.meadows < 0:
            raise ConfigError('[grass] meadows is a count, 0 or more')
        if not 0 <= self.base <= 1:
            raise ConfigError('[grass] base is a share of full cover, 0 to 1')
        if min(self.regrow, self.bite, self.still, self.food) < 0:
            raise ConfigError('[grass] regrow, bite, still and food are 0 or more')
        if self.on and (self.cell <= 0 or self.radius <= 0 or self.distance < 0):
            raise ConfigError('[grass] cell and radius are above 0 and distance 0 or more')

    @property
    def on(self) -> bool:
        return self.meadows > 0 or self.base > 0


@dataclass(frozen=True)
class Tired:
    drain: float
    rest: float
    still: float
    below: float
    slowest: float
    # `rest` is worth this many times as much while warm (in the nest or huddled), and again while still in the dark
    warm: float = 1.0
    dark: float = 1.0

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
    stoop: float
    lift: float

    @property
    def on(self) -> bool:
        return self.reach > 0


@dataclass(frozen=True)
class Dung:
    every: int
    after: float
    lasts: float
    slots: int
    radius: float
    near: float
    sick: float
    away: float
    pile: float
    start: int
    midden: float
    points: float
    spot: float
    heap: int
    wander: float
    move: float      # the spot moves somewhere new every this many seconds, its heap with it (0: never)

    @property
    def on(self) -> bool:
        return self.every > 0 or self.start > 0


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
    sense: bool     # the flags' compass: how far each is and which way, from anywhere (off: only what the rays see)

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
class Jump:
    height: float    # metres a jump from standing lifts a nim (0: it can't jump)
    energy: float    # each jump costs this

    @property
    def on(self) -> bool:
        return self.height > 0


@dataclass(frozen=True)
class Tree:
    trunk: int       # the block that is its trunk
    near: float      # apples hang between these distances (m) from the trunk's middle
    far: float
    reach: float     # how high (m) a nim has to jump to take one (0: from the ground)
    points: float    # for each apple taken (0 is off)
    hop: float       # what each jump costs, in the same points, so hopping all the time doesn't pay
    home: bool       # an apple taken goes in the crop, and pays only once it's unloaded in the nest
    move: float      # the tree moves every this many seconds, where [arena] scatter would put it (0: never)
    start: float     # every episode starts with each nim this far (m) from the trunk, facing it (0: at the nest)
    burrow: bool     # unloading an apple at home takes the carrier down into the nest, back up at its middle turned any way

    def __post_init__(self):
        if self.start < 0:
            raise ConfigError('[tree] start can\'t be below 0')
        if self.start > 0 and self.points <= 0:
            raise ConfigError('[tree] start needs the tree on ([tree] points above 0)')
        if self.burrow and not (self.points > 0 and self.home):
            raise ConfigError('[tree] burrow needs apples carried home ([tree] points above 0 and home)')

    @property
    def on(self) -> bool:
        return self.points > 0


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
    home: Home
    food: Food
    crop: Crop
    jelly: Jelly
    hatch: Hatch
    young: Young
    night: Night
    water: Water
    grass: Grass
    sprint: Sprint
    tired: Tired
    flowers: Flowers
    grab: Grab
    carry: Carry
    dung: Dung
    smell: Smell
    hearing: Hearing
    tag: Tag
    seek: Seek
    flag: Flag
    peek: Peek
    jump: Jump
    tree: Tree
    ground: Ground
    vision: Vision
    episode: Episode
    block: tuple[Block, ...]
    # sections added since, left out of a world file they're off: lab worlds from before still load
    fat: Fat = dataclasses.field(default_factory=Fat)

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
    needs: float
    needs_lost: float
    dawn: float


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
    # a field with a default may be left out (the keys added since most worlds were written)
    optional = {f.name for f in dataclasses.fields(cls) if f.default is not dataclasses.MISSING
                or f.default_factory is not dataclasses.MISSING}
    if missing := sorted(names - optional - set(data)):
        raise ConfigError(f'{where}: missing key(s) {", ".join(missing)}')
    return cls(**{name: convert(hints[name], data[name], f'{where}.{name}') for name in names if name in data})


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
         'night': {'cycle': 0.0, 'length': 0.0, 'dusk': 0.0, 'cold': 0.0, 'nest': 0.0, 'huddle': 0.0, 'reach': 0.0, 'start_dark': 0.0, 'chill_time': 20.0},
         'water': {'ponds': 0, 'radius': 0.0, 'distance': 0.0, 'drain': 0.0, 'drink': 0.0, 'still': 0.0, 'start': 1.0},
         'grass': {'cell': 0.5, 'meadows': 0, 'radius': 0.0, 'distance': 0.0, 'base': 0.0, 'regrow': 0.0, 'bite': 0.0, 'still': 0.0, 'food': 0.0},
         'energy': {'turn': 0.0},
         'hatch': {'cost': 0, 'threshold': 0, 'seconds': 0.0},
         'young': {'seconds': 0.0, 'speed': 1.0, 'energy': 1.0, 'start': False},
         'tag': {'reach': 0.0, 'cooldown': 0.0, 'points': 0.0, 'speed': 1.0, 'back': -1.0},
         'seek': {'prep': 0.0, 'points': 0.0},
         'flag': {'points': 0.0, 'pickup': 0.0, 'charge': 1.0, 'home': 0.0, 'steal': False, 'guard': 0.0, 'lie': 0.0, 'sense': True},
         'peek': {'show': 0.0, 'points': 0.0, 'gap': 0.0, 'timeout': 0.0, 'near': 0.0, 'far': 0.0, 'spin': False, 'again': 0.0, 'flash': 0.0},
         'sprint': {'speed': 1.0, 'seconds': 0.0, 'cooldown': 0.0, 'energy': 0.0},
         'tired': {'drain': 0.0, 'rest': 0.0, 'still': 0.0, 'below': 0.0, 'slowest': 1.0},
         'food': {'middle': 0},
         'flowers': {'count': 0, 'every_min': 0.0, 'every_max': 0.0, 'open': 0.0, 'radius': 0.0, 'food': 0, 'boost': 0.0,
                     'speed': 1.0, 'spots': 0, 'spot_gap': 0.0},
         'grab': {'reach': 0.0, 'grip': 0.0, 'seconds': 0.0, 'energy': 0.0},
         'carry': {'reach': 0.0, 'slow': 0.0, 'energy': 0.0, 'stoop': 0.0, 'lift': 0.0},
         'smell': {'cell': 0.0, 'spread': 0.0, 'fade': 0.0, 'leak': 0.0},
         'hearing': {'range': 0.0},
         'dung': {'every': 0, 'after': 0.0, 'lasts': 0.0, 'slots': 0, 'radius': 0.0, 'near': 0.0, 'sick': 0.0, 'away': 1.0,
                  'pile': 0.0, 'start': 0, 'midden': 0.0, 'points': 0.0,
                  'spot': 0.0, 'heap': 0, 'wander': 0.0, 'move': 0.0},
         'jump': {'height': 0.0, 'energy': 0.0},
         'tree': {'trunk': 0, 'near': 0.0, 'far': 0.0, 'reach': 0.0, 'points': 0.0, 'hop': 0.0, 'home': False, 'move': 0.0, 'start': 0.0, 'burrow': False},
         'home': {'near': 0.0, 'far': 0.0, 'compass': True}}


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
