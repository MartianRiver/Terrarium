# World config, read from a TOML file. There are no defaults here on purpose:
# every number lives in the file, so a run record's copy of it is the whole story.

import dataclasses
import tomllib
import typing
from dataclasses import dataclass
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / 'configs' / 'world.toml'


@dataclass(frozen=True)
class Arena:
    size: float


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
    food: float


@dataclass(frozen=True)
class Colonies:
    count: int
    size: int
    nest_radius: float
    nest_distance: float
    spawn_ring: float


@dataclass(frozen=True)
class Food:
    count: int
    radius: float
    regrow_min: float
    regrow_max: float
    clearance: float


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


@dataclass(frozen=True)
class Vision:
    rays: int
    fov: float
    range: float


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
    ground: Ground
    vision: Vision
    episode: Episode
    block: tuple[Block, ...]

    @property
    def dt(self) -> float:
        return 1 / self.tick_hz

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
    # TOML ints are fine where a float is wanted, but not the other way round, and never bools
    if isinstance(value, bool) or not (isinstance(value, kind) or (kind is float and isinstance(value, int))):
        raise ConfigError(f'{where}: expected {kind.__name__}, got {value!r}')
    return kind(value)


def load(path: Path | str = DEFAULT) -> Config:
    with open(path, 'rb') as f:
        return build(Config, tomllib.load(f))
