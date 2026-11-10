# Save a world at a tick boundary and resume it later, on this machine or another, to carry on bit for bit.
#
# What a save holds: every array, counter, id, clock and random stream the world and its mechanics have (found by
# walking their attributes, so a new mechanic is saved without being listed here, and one that holds something that
# can't be saved fails loudly instead of being dropped), the physics spaces, the config and the code's commit, and a
# frozen brain's own state if the caller hands it over. Loading refuses a different config.
#
# Physics is the catch. Pymunk pickles a space, but a space rebuilt from that isn't the one it came from: the solver's
# memory of last step's contact impulses is gone, and the broadphase tree is laid out afresh, so contacts that form
# later are solved in another order and the floats come out a few bits apart (seen at tick +8 on a save where nothing
# touched). A restore is deterministic though, so save() has two ways to make the world and its resume agree:
#
#   settle (the default): the live world takes the same trip through the file, so from here on it and any resume of it
#   are identical bit for bit. It's a one-step perturbation (warm start dropped, tree rebuilt), invisible in play but
#   not nothing: a world that saves is a different, equally valid, run from one that never did, and a save is an event
#   in its history. Bodies and spaces are replaced, so nothing may hold on to one across a save.
#
#   journal: pass the Journal the world has been driven through and the live world is left alone (exact against a world
#   that never saved); the file holds the actions too and load(replay_journal=True) re-runs them. As slow to restore
#   as the world is old, and everything that steps or resets the world has to go through the journal.
#
# Resuming needs the same code and libraries; floats across machines and CPU families are not checked.
#
#   uv run python -m terrarium.save --check WORLD.toml [BRAIN.pt] [--arenas N]

import argparse
import functools
import hashlib
import io
import pickle
import subprocess
import tempfile
import time
from dataclasses import dataclass, is_dataclass
from pathlib import Path

import numpy as np

from .config import Config, build, load as load_config
from .log import Logger
from .physics import Physics
from .world import World

log = Logger('save')

FORMAT = 1
# the world's own attributes that aren't part of the saved state walk
SKIP = frozenset({'cfg', 'physics', 'world'})
PHYSICS_SKIP = frozenset({'cfg', 'spaces', 'bodies', 'held', 'reads', 'writes'})
# what a save file may name when it's unpickled: a guard against a file that isn't one of ours, not a sandbox
SAFE = ('numpy', 'pymunk', 'collections', 'copyreg', '_codecs', 'terrarium.save')
BUILTINS = {'set', 'frozenset', 'bytearray', 'complex', 'slice', 'range'}
NOT_NUMPY = ('load', 'save', 'fromfile', 'memmap', 'genfromtxt', 'loadtxt', 'savetxt', 'testing', 'f2py', 'ctypeslib', 'lib')


# a value that's the config's own (a section, or the blocks): rebuilt from it, not saved
IN_CONFIG = ('config',)


def is_config(v) -> bool:
    return is_dataclass(v) or (isinstance(v, tuple) and len(v) > 0 and all(is_dataclass(x) for x in v))


class SaveError(Exception):
    pass


class Mismatch(SaveError):
    """The save was made with another config, or can't be checked against the one given."""


class Stream:
    """A random stream's state."""

    def __init__(self, state):
        self.state = state


class Part(dict):
    """The saved attributes of one object a world owns."""


class Reader(pickle.Unpickler):
    def find_class(self, module, name):
        ok = (name in BUILTINS) if module == 'builtins' else module.split('.')[0] in SAFE or module in SAFE
        if module.startswith('numpy') and (name.startswith(NOT_NUMPY) or module.split('.')[-1] in NOT_NUMPY):
            ok = False
        if not ok:
            raise SaveError(f'save file wants {module}.{name}, which a save has no business holding')
        return super().find_class(module, name)


def read(data: bytes):
    return Reader(io.BytesIO(data)).load()


# --- walking a world's attributes

def pack(v, path: str, world):
    if v is None or isinstance(v, (bool, int, float, str, bytes, np.generic)):
        return v
    if isinstance(v, np.ndarray):
        if v.dtype == object:
            raise SaveError(f'{path}: an array of objects')
        return v.copy()
    if isinstance(v, np.random.Generator):
        return Stream(v.bit_generator.state)
    if is_config(v):
        return IN_CONFIG
    if isinstance(v, (list, tuple)):
        return type(v)(pack(x, f'{path}[{i}]', world) for i, x in enumerate(v))
    if isinstance(v, dict):
        return {pack(k, path, world): pack(x, f'{path}[{k!r}]', world) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return set(v)
    if type(v).__module__.startswith('terrarium') and hasattr(v, '__dict__') and not callable(v):
        return pack_object(v, path, world)
    raise SaveError(f'{path}: {type(v).__name__} can\'t be saved (a function, closure or foreign object?)')


def pack_object(obj, path: str, world, skip=frozenset()) -> Part:
    out = Part()
    for key, v in vars(obj).items():
        if key in skip or v is world:
            continue
        packed = pack(v, f'{path}.{key}', world)
        if packed is not IN_CONFIG:
            out[key] = packed
    return out


def unpack(old, saved, path: str, world):
    """The value to put where `old` is: arrays, streams, lists and parts are filled in place, so anything holding
    the same object (a view, another list's entry) still sees it."""
    if isinstance(saved, Stream):
        if not isinstance(old, np.random.Generator):
            raise Mismatch(f'{path}: saved a random stream, the world has {type(old).__name__}')
        old.bit_generator.state = saved.state
        return old
    if isinstance(saved, np.ndarray):
        if isinstance(old, np.ndarray) and old.shape == saved.shape and old.dtype == saved.dtype:
            old[...] = saved
            return old
        return saved.copy()
    if isinstance(saved, Part):
        if old is None or not hasattr(old, '__dict__'):
            raise Mismatch(f'{path}: saved a part the world doesn\'t have')
        unpack_object(old, saved, path, world)
        return old
    if isinstance(saved, list):
        if isinstance(old, list) and len(old) == len(saved):
            old[:] = [unpack(o, s, f'{path}[{i}]', world) for i, (o, s) in enumerate(zip(old, saved))]
            return old
        return [unpack(None, s, path, world) for s in saved]
    if isinstance(saved, tuple):
        olds = old if isinstance(old, tuple) and len(old) == len(saved) else (None,) * len(saved)
        return tuple(unpack(o, s, f'{path}[{i}]', world) for i, (o, s) in enumerate(zip(olds, saved)))
    if isinstance(saved, dict):
        olds = old if isinstance(old, dict) else {}
        new = {k: unpack(olds.get(k), s, f'{path}[{k!r}]', world) for k, s in saved.items()}
        if isinstance(old, dict):
            old.clear()
            old.update(new)
            return old
        return new
    if isinstance(saved, set):
        return set(saved)
    return saved


def unpack_object(obj, saved: Part, path: str, world, skip=frozenset()):
    here = {k for k, v in vars(obj).items() if k not in skip and v is not world and not is_config(v)}
    extra = here - set(saved)
    missing = set(saved) - here
    if extra or missing:
        raise Mismatch(f'{path}: attributes differ from the save (new here: {sorted(extra)}, only in the save: {sorted(missing)})')
    for key, s in saved.items():
        setattr(obj, key, unpack(getattr(obj, key), s, f'{path}.{key}', world))


def parts(world: World) -> dict[str, object]:
    """The mechanics a world owns, by attribute name."""
    return {k: v for k, v in vars(world).items() if k not in SKIP and type(v).__module__.startswith('terrarium')}


def state(world: World) -> Part:
    return pack_object(world, 'world', world, SKIP)


def physics_state(physics: Physics, world: World) -> dict:
    blob = pickle.dumps((physics.spaces, physics.bodies, physics.held), protocol=5)
    return {'attrs': pack_object(physics, 'physics', world, PHYSICS_SKIP), 'spaces': blob}


def apply_physics(physics: Physics, saved: dict, world: World):
    physics.spaces, physics.bodies, physics.held = read(saved['spaces'])
    unpack_object(physics, saved['attrs'], 'physics', world, PHYSICS_SKIP)


# --- the journal

class Journal:
    """What a world was told since it began: every step's actions and every reset, so a copy can be rebuilt by doing
    them again. Everything that touches the world has to go through it (world.step and world.reset alone)."""

    def __init__(self):
        self.entries: list[tuple] = []

    def step(self, world: World, actions: np.ndarray):
        self.entries.append(('step', np.array(actions, copy=True)))
        world.step(actions)

    def reset(self, world: World, arenas: np.ndarray):
        self.entries.append(('reset', np.array(arenas, copy=True)))
        world.reset(arenas)


def replay(cfg: Config, arenas: int, seed: int, entries: list) -> World:
    world = World(cfg, arenas, seed)
    for kind, arg in entries:
        world.step(arg) if kind == 'step' else world.reset(arg)
    return world


# --- save and load

@functools.cache
def commit() -> tuple[str, bool]:
    here = Path(__file__).resolve().parent
    try:
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=here, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=here, capture_output=True, text=True,
                                    check=True).stdout.strip())
        return head, dirty
    except (OSError, subprocess.CalledProcessError):
        return 'unknown', False


@dataclass
class Saved:
    tick: int
    bytes: int
    settled: bool       # the live world's physics was rebuilt from the file; False: left as it was


def save(world: World, path: Path | str, policy_state=None, journal: Journal | None = None) -> Saved:
    """The world as it stands between two ticks, with `policy_state` (what the brain driving it gives:
    evals.brain_policy's act.state()). Without a journal the live world's physics is settled (see the top of the
    file); with one it's left alone and the file can be replayed."""
    head, dirty = commit()
    doc = {
        'format': FORMAT, 'config': world.cfg.to_dict(), 'arenas': world.arenas, 'seed': world.seed, 'tick': world.tick,
        'commit': head, 'dirty': dirty, 'state': state(world), 'policy': policy_state,
        'physics': physics_state(world.physics, world),
        'journal': None if journal is None else journal.entries,
    }
    data = pickle.dumps(doc, protocol=5)
    path = Path(path)
    tmp = path.with_name(path.name + '.part')
    tmp.write_bytes(data)
    tmp.replace(path)
    if journal is None:
        apply_physics(world.physics, doc['physics'], world)
    log.info('world saved', tick=world.tick, bytes=len(data), journal=journal is not None)
    return Saved(world.tick, len(data), journal is None)


def load(path: Path | str, cfg: Config | None = None, replay_journal: bool = False, strict_code: bool = False):
    """(world, policy_state) as saved. With `cfg`, refuses a save made under a different one; without, builds the
    world from the config in the file. replay_journal re-runs the saved journal instead of restoring physics, then
    checks the result against the saved state."""
    doc = read(Path(path).read_bytes())
    if doc['format'] != FORMAT:
        raise SaveError(f'save format {doc["format"]}, this code reads {FORMAT}')
    saved_cfg = build(Config, doc['config'])
    if cfg is not None and cfg.to_dict() != doc['config']:
        raise Mismatch(f'config differs from the one this world was saved under: {differences(doc["config"], cfg.to_dict())}')
    cfg = saved_cfg
    head, _ = commit()
    if head != doc['commit']:
        message = f'saved under commit {doc["commit"][:10]}{" (dirty)" if doc["dirty"] else ""}, this is {head[:10]}'
        if strict_code:
            raise Mismatch(message)
        log.warn('code differs from the save', detail=message)
    if replay_journal:
        if doc['journal'] is None:
            raise SaveError('this save has no journal (save() was not given one)')
        world = replay(cfg, doc['arenas'], doc['seed'], doc['journal'])
        check = state(world)
        if not same(check, doc['state']) or world.tick != doc['tick']:
            raise SaveError('replaying the journal did not reach the saved state')
    else:
        world = World(cfg, doc['arenas'], doc['seed'])
        unpack_object(world, doc['state'], 'world', world, SKIP)
        apply_physics(world.physics, doc['physics'], world)
    return world, doc['policy']


def differences(a, b, path='') -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += differences(a.get(k), b.get(k), f'{path}.{k}' if path else k)
        return out
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f'{path}[{i}]')]
    return [] if a == b else [f'{path}: saved {a!r}, now {b!r}']


def same(a, b) -> bool:
    """Equal down to the bytes of every array and the state of every stream."""
    return not unlike(a, b)


def unlike(a, b, path='') -> list[str]:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        ok = isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
        return [] if ok else [path]
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return [f'{path} (keys)']
        return [d for k in a for d in unlike(a[k], b[k], f'{path}.{k}' if isinstance(a, Part) else f'{path}[{k!r}]')]
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return [f'{path} (length)']
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in unlike(x, y, f'{path}[{i}]')]
    if isinstance(a, Stream) and isinstance(b, Stream):
        return unlike(a.state, b.state, path)
    if isinstance(a, float) and isinstance(b, float):
        return [] if np.float64(a).tobytes() == np.float64(b).tobytes() else [path]
    return [] if type(a) is type(b) and a == b else [path]


def fingerprint(world: World) -> dict:
    """Everything that makes the world what it is, to compare two worlds: the walked state, the bodies' every field
    and the arrays physics keeps."""
    out: dict[str, object] = {'world': state(world), 'physics': pack_object(world.physics, 'physics', world, PHYSICS_SKIP)}
    out['bodies'] = [[(tuple(b.position), b.angle, tuple(b.velocity), b.angular_velocity, tuple(b.force), b.torque,
                       [(s.filter.categories, s.filter.mask) for s in b.shapes]) for b in bodies] for bodies in world.physics.bodies]
    out['joints'] = [[(type(c).__name__, c.max_force, c.max_bias, c.impulse) for c in space.constraints] for space in world.physics.spaces]
    return out


def digest(world: World) -> str:
    """A short hash of fingerprint(world), to compare worlds in different processes."""
    h = hashlib.sha256()

    def feed(v):
        if isinstance(v, np.ndarray):
            h.update(f'{v.dtype}{v.shape}'.encode() + v.tobytes())
        elif isinstance(v, Stream):
            feed(v.state)
        elif isinstance(v, dict):
            for k in sorted(v, key=repr):
                h.update(repr(k).encode())
                feed(v[k])
        elif isinstance(v, (list, tuple)):
            h.update(f'[{len(v)}'.encode())
            for x in v:
                feed(x)
        elif isinstance(v, float):
            h.update(np.float64(v).tobytes())
        else:
            h.update(repr(v).encode())
    feed(fingerprint(world))
    return h.hexdigest()[:16]


def check(world_toml: str, brain: str | None, arenas: int, before: int, after: int) -> bool:
    """Run a world `before` ticks, save, run `after` more, then do the same from the file in a fresh World and compare
    every tick. Prints what it found."""
    from .evals import brain_policy
    from .schema import ACTIONS

    cfg = load_config(world_toml)

    def driver(world):
        if brain:
            return brain_policy(brain, 'drawn')(world)
        a, c, k = np.arange(world.arenas)[:, None, None], np.arange(len(world.colony))[None, :, None], np.arange(len(ACTIONS))[None, None, :]
        return lambda w: np.where(k == 0, np.abs(np.sin(w.tick * 0.07 * (a + 1.0) + c)) * 0.8 + 0.4, np.sin(w.tick * 0.07 * (a + 1.0) + c + 1.7 * k))

    def play(world, act, ticks):
        out = []
        for _ in range(ticks):
            world.step(act(world))
            out.append(digest(world))
        return out

    world = World(cfg, arenas, 4_100_000)
    act = driver(world)
    play(world, act, before)
    path = Path(tempfile.mkdtemp()) / 'world.save'
    t0 = time.perf_counter()
    info = save(world, path, policy_state=getattr(act, 'state')() if hasattr(act, 'state') else None)
    t_save = time.perf_counter() - t0
    live = play(world, act, after)
    t0 = time.perf_counter()
    resumed, brain_state = load(path, cfg)
    t_load = time.perf_counter() - t0
    again = driver(resumed)
    if brain_state is not None:
        getattr(again, 'restore')(brain_state)
    mine = play(resumed, again, after)
    bad = next((i for i, (x, y) in enumerate(zip(live, mine)) if x != y), None)
    print(f'{arenas} arenas, {before} ticks then {after}: {info.bytes / 1e3:.0f} kB, save {t_save * 1e3:.0f} ms, load {t_load * 1e3:.0f} ms')
    print('exact on every tick' if bad is None else f'DIFFERS {bad + 1} ticks after the save')
    return bad is None


def main():
    p = argparse.ArgumentParser(description='save a world mid-run, resume it, and compare every tick')
    p.add_argument('--check', required=True, metavar='WORLD.toml')
    p.add_argument('brain', nargs='?', help='a frozen brain to drive it (else plain scripted actions)')
    p.add_argument('--arenas', type=int, default=2)
    p.add_argument('--before', type=int, default=60)
    p.add_argument('--after', type=int, default=120)
    a = p.parse_args()
    raise SystemExit(0 if check(a.check, a.brain, a.arenas, a.before, a.after) else 1)


if __name__ == '__main__':
    # through the package, so Stream and Part pickle as terrarium.save.*, not __main__.*
    from terrarium.save import main as run_main
    run_main()
