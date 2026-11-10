import pickle
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from terrarium import load as load_config
from terrarium import save as saves
from terrarium.brain import SHAPE, Brain
from terrarium.brain import save as save_brain
from terrarium.evals import brain_policy
from terrarium.save import Journal, Mismatch, digest, fingerprint, load, unlike
from terrarium.schema import ACTIONS
from terrarium.world import World

from test_memory import shaken

DATA = Path(__file__).parent / 'data'
SEED = 4_100_000


def colony(hatch_seconds: float = 4.0):
    cfg = load_config(DATA / 'colony-2x9.toml')
    # an egg that hatches, and a night that falls, within a test's length
    return replace(cfg, hatch=replace(cfg.hatch, seconds=hatch_seconds), night=replace(cfg.night, cycle=8.0, length=4.0, dusk=1.0))


def actions(world: World, tick: int) -> np.ndarray:
    """Each arena's own, from the tick alone: everyone heads off and turns about, so they meet."""
    a = np.arange(world.arenas)[:, None, None]
    c = np.arange(world.alive.shape[1])[None, :, None]
    k = np.arange(len(ACTIONS))[None, None, :]
    out = np.sin(tick * 0.07 * (a + 1.0) + c + 1.7 * k)
    out[..., 0] = np.abs(out[..., 0]) * 0.8 + 0.4
    return out


def rich(world: World):
    """Jelly in every store, so an egg is laid at once into each empty place."""
    world.store[:] = 12


def touching(world: World) -> bool:
    """Two live creatures in contact, in any arena."""
    r = world.cfg.creature.radius
    for a in range(world.arenas):
        live = world.pos[a][world.alive[a]]
        d = np.hypot(*(live[:, None] - live[None]).transpose(2, 0, 1))
        if ((d < 2 * r + 0.02) & ~np.eye(len(live), dtype=bool)).any():
            return True
    return False


def run(world: World, ticks: range, step=None, keep=None, policy=None):
    """Step through these ticks, playing `policy`'s actions or the plain ones; what `keep(world)` gave after each."""
    seen = []
    for t in ticks:
        act = policy(world) if policy else actions(world, t)
        (step or world.step)(act)
        if keep:
            seen.append(keep(world))
    return seen


def until_touching(world: World, start: int = 0, step=None, limit: int = 400) -> int:
    """Step the world until two creatures touch; the tick it's then at."""
    t = start
    while not touching(world):
        (step or world.step)(actions(world, t))
        t += 1
        assert t < limit, 'nothing ever touched'
    return t


def assert_continues(live: list, resumed: list, what: str):
    assert len(live) == len(resumed) > 0
    for i, (x, y) in enumerate(zip(live, resumed)):
        bad = unlike(x, y)
        assert not bad, f'{what}: differs {i + 1} ticks after the save, in {bad[:6]}'


def test_walk_finds_everything_and_refuses_what_it_cant_hold():
    world = World(colony(), 2, SEED)
    state = saves.state(world)
    # every attribute of the world and its mechanics, none left out
    assert {'rngs', 'tie_rngs', 'food_regrow', 'egg', 'store', 'next_id', 'smell', 'grass', '_nest_ranks', 'maze_open'} <= set(state)
    assert 'cover' in state['grass'] and 'smell' in state['smell']
    assert {k for k in vars(world) if k not in saves.SKIP} == set(state)
    world.hook = lambda: 1
    with pytest.raises(saves.SaveError, match='world.hook'):
        saves.state(world)


def test_a_save_is_refused_into_a_different_config(tmp_path):
    cfg = colony()
    world = World(cfg, 2, SEED)
    saves.save(world, tmp_path / 'w.save')
    with pytest.raises(Mismatch, match='food.count'):
        load(tmp_path / 'w.save', replace(cfg, food=replace(cfg.food, count=cfg.food.count + 1)))
    resumed, _ = load(tmp_path / 'w.save', cfg)
    assert not unlike(fingerprint(world), fingerprint(resumed))
    # a file that isn't a save of ours is not run
    (tmp_path / 'evil.save').write_bytes(pickle.dumps({'format': 1, 'x': print}))
    with pytest.raises(saves.SaveError, match='builtins.print'):
        load(tmp_path / 'evil.save')


@pytest.mark.parametrize('arenas', [1, 4])
@pytest.mark.parametrize('where', ['nobody near anybody', 'in contact'])
def test_resume_plays_the_same_ticks_bit_for_bit(tmp_path, arenas, where):
    """A copy loaded into a new World object plays every tick the live world does, byte for byte in every array, body
    and random stream: through eggs hatching, a night, grass and food growing back, and contacts."""
    cfg = colony()
    world = World(cfg, arenas, SEED)
    rich(world)
    # three berries that are somewhere between eaten and grown back, one of them past the night
    world.food_regrow[:, :3] = (30, 90, 400)
    if where == 'in contact':
        # a few seconds in, with grass grazed and eggs laid but not yet hatched
        run(world, range(45))
        start = until_touching(world, 45)
        assert world.grazed.sum() > 0
    else:
        run(world, range(1))
        start = 1
    assert touching(world) == (where == 'in contact') and (world.egg > 0).any()
    info = saves.save(world, tmp_path / 'w.save')
    assert info.settled
    live = run(world, range(start, start + 170), keep=fingerprint)
    resumed, _ = load(tmp_path / 'w.save', cfg)
    again = run(resumed, range(start, start + 170), keep=fingerprint)
    assert_continues(live, again, where)
    # the stretch was eventful: a night fell and ended, eggs hatched, grass was eaten, berries grew back
    dark = [fp['world']['dark'].any() for fp in live]
    assert any(dark) and not dark[-1] and world.hatched.sum() > 0 and world.grazed.sum() > 0
    assert (world.food_regrow[:, :world.wild] > 0).any() and (world.food_regrow[:, :3] != 400).all()


def test_a_restored_space_isnt_the_one_it_came_from():
    """Why save() settles the live world: pymunk's pickle drops the solver's contact memory and relays the broadphase
    tree, so a restore that the live world didn't take parts from it, here by the time the first contacts form."""
    cfg = colony()
    world = World(cfg, 1, SEED)
    run(world, range(1))
    copy = World(cfg, 1, SEED)
    saves.unpack_object(copy, saves.state(world), 'world', copy, saves.SKIP)
    saves.apply_physics(copy.physics, saves.physics_state(world.physics, world), copy)
    assert not unlike(fingerprint(world), fingerprint(copy))
    live, again = (run(w, range(1, 200), keep=fingerprint) for w in (world, copy))
    assert any(unlike(x, y) for x, y in zip(live, again))
    # and it is only the physics: the game's own arrays still agree until a contact makes them part
    assert not unlike(live[0]['world'], again[0]['world'])


def test_journal_replay_is_exact_and_leaves_the_live_world_alone(tmp_path):
    """The other way: the actions saved instead of the solver's memory, and a resume does them again. The live world
    is as it would have been had it never saved, so it matches one that didn't, and so does the replay. (A store
    filled by hand, outside the journal, makes the replay fail its check: see rich() above.)"""
    cfg = colony()
    journal, world, never = Journal(), World(cfg, 2, SEED), World(cfg, 2, SEED)
    run(world, range(40), step=lambda a: journal.step(world, a))
    run(never, range(40))
    # an arena starting over partway is part of the journal too
    journal.reset(world, np.array([False, True]))
    never.reset(np.array([False, True]))
    tick = until_touching(world, 40, step=lambda a: journal.step(world, a))
    until_touching(never, 40)
    info = saves.save(world, tmp_path / 'w.save', journal=journal)
    assert not info.settled
    live = run(world, range(tick, tick + 100), keep=fingerprint)
    unsaved = run(never, range(tick, tick + 100), keep=fingerprint)
    assert_continues(live, unsaved, 'a journalled save leaves the world alone')
    resumed, _ = load(tmp_path / 'w.save', cfg, replay_journal=True)
    again = run(resumed, range(tick, tick + 100), keep=fingerprint)
    assert_continues(live, again, 'journal replay')
    # replaying checks itself against the saved arrays: a different journal can't pass for the world
    doc = saves.read((tmp_path / 'w.save').read_bytes())
    doc['journal'] = doc['journal'][:-1]
    (tmp_path / 'short.save').write_bytes(pickle.dumps(doc))
    with pytest.raises(saves.SaveError, match='did not reach'):
        load(tmp_path / 'short.save', cfg, replay_journal=True)
    saves.save(never, tmp_path / 'n.save')
    with pytest.raises(saves.SaveError, match='no journal'):
        load(tmp_path / 'n.save', cfg, replay_journal=True)


def test_a_frozen_brain_and_its_notes_carry_on_across_a_save(tmp_path):
    """The brain's own state goes with the world: its notes, last steering, held choice, decision phase and the streams
    its yes/no actions are drawn from. Compared tick by tick."""
    cfg = colony()
    save_brain(shaken(Brain(**SHAPE).with_memory(8), seed=3), tmp_path / 'b.pt')
    make = brain_policy(tmp_path / 'b.pt', mode='drawn')
    world = World(cfg, 2, SEED)
    rich(world)
    act = make(world)
    run(world, range(45), policy=act)
    assert act.state()['ticks'] == 45 and np.abs(act.state()['notes']).sum() > 0
    saves.save(world, tmp_path / 'w.save', policy_state=act.state())
    live = run(world, range(60), policy=act, keep=lambda w: (fingerprint(w), act.state()))
    resumed, brain_state = load(tmp_path / 'w.save', cfg)
    fresh = make(resumed)
    fresh.restore(brain_state)
    again = run(resumed, range(60), policy=fresh, keep=lambda w: (fingerprint(w), fresh.state()))
    assert_continues(live, again, 'brain and world')
    # a brain not given its state back doesn't carry on the same
    blank = make(resumed2 := load(tmp_path / 'w.save', cfg)[0])
    other = run(resumed2, range(60), policy=blank, keep=fingerprint)
    assert any(unlike(x, y[0]) for x, y in zip(other, live))


def test_a_resume_in_a_fresh_process_plays_the_same_ticks(tmp_path):
    cfg = colony()
    world = World(cfg, 2, SEED)
    rich(world)
    run(world, range(30))
    saves.save(world, tmp_path / 'w.save')
    live = [digest(w) for t in range(30, 90) for w in [world] if not run(world, range(t, t + 1))]
    script = f"""
import sys
sys.path.insert(0, {str(Path(__file__).parent)!r})
from terrarium.save import load, digest
from test_save import colony, run
w, _ = load({str(tmp_path / 'w.save')!r}, colony())
for t in range(30, 90):
    run(w, range(t, t + 1))
    print(digest(w))
"""
    there = subprocess.run([sys.executable, '-I', '-c', script], capture_output=True, text=True, check=True).stdout.split()
    assert there == live and len(set(live)) == 60


def test_no_arrays_share_memory_so_in_place_restores_cant_cross():
    world = World(colony(), 2, SEED)
    arrays = [(f'{name}.{k}', v) for name, owner in {'world': world, **saves.parts(world)}.items()
              for k, v in vars(owner).items() if isinstance(v, np.ndarray) and v.size]
    for i, (n1, a1) in enumerate(arrays):
        for n2, a2 in arrays[i + 1:]:
            assert not np.shares_memory(a1, a2), f'{n1} and {n2} share memory'
