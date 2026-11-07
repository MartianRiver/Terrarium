import numpy as np
import pytest

from terrarium import load, replay
from terrarium.brain import SHAPE, Brain, save
from terrarium.config import DEFAULT
from terrarium.ghost import SHOW, Readout, Trail, fit_notes
from terrarium.record import record
from terrarium.world import World

MEMORY = 16
TREE = load(DEFAULT.parent / 'nursery-tree-home.toml')


def readout(brain='', memory=MEMORY):
    return Readout(brain, 'test', 10, 1, np.ones(memory, bool), np.zeros(memory), np.ones(memory),
                   np.tile([1.0, 0.0], (memory, 1)) / memory, np.array([2.0, -1.0]), 1.0, 0.5, 5.0, 100)


def test_apply_standardises_then_reads_the_weights():
    r = Readout('b', 'w', 1, 1, np.array([True, False, True]), np.array([1.0, 0.0]), np.array([2.0, 4.0]),
                np.array([[1.0, 0.0], [0.0, 2.0]]), np.array([0.5, -0.5]), 1.0, 0.0, 0.0, 0)
    got = r.apply(np.array([[3.0, 99.0, 4.0], [1.0, 0.0, 0.0]]))
    # (3-1)/2 = 1 and (4-0)/4 = 1 for the first; the middle note is ignored
    assert np.allclose(got, [[1.5, 1.5], [0.5, -0.5]])


def test_a_fit_finds_known_weights_and_scores_held_out_games(tmp_path):
    rng = np.random.default_rng(0)
    n = 1500
    notes = rng.normal(size=(n, 8)) * rng.uniform(0.5, 3, 8)
    notes[:, 5] = 0.7
    true_w = rng.normal(size=(8, 2))
    tree = notes @ true_w + np.array([3.0, -2.0]) + rng.normal(scale=0.05, size=(n, 2))
    game = np.arange(n) // 5
    r = fit_notes(notes, tree, game, 'brain', 'world', 7)
    assert not r.keep[5] and r.keep.sum() == 7
    fresh = rng.normal(size=(200, 8))
    fresh[:, 5] = 0.7
    assert np.abs(r.apply(fresh) - (fresh @ true_w + [3.0, -2.0])).max() < 0.5
    assert r.median_m < 0.2 and r.median_deg < 3
    assert (r.brain, r.world, r.seed, r.games) == ('brain', 'world', 7, 300)

    r.save(tmp_path / 'r.npz')
    back = Readout.load(tmp_path / 'r.npz')
    assert back.brain == 'brain' and np.array_equal(back.keep, r.keep)
    assert np.allclose(back.apply(fresh), r.apply(fresh))


def memory_brain(path):
    return save(Brain(**SHAPE).with_memory(MEMORY), path)


def deposit_at(monkeypatch, tick):
    # a random brain won't carry an apple home in a short run: say one was unloaded
    step = World.step

    def stepped(self, action):
        step(self, action)
        if self.tick == tick:
            self.stored[0, 0] += 1

    monkeypatch.setattr(World, 'step', stepped)


def test_a_replay_gets_ghosts_only_after_a_deposit_and_for_a_while(tmp_path, monkeypatch):
    pt = tmp_path / 'b.pt'
    r = readout(memory_brain(pt))
    r.save(tmp_path / 'r.npz')
    deposit_at(monkeypatch, 30)
    hz = TREE.tick_hz
    record(TREE, tmp_path / 'g.jsonl.gz', 40 + round((SHOW + 2) * hz), seed=1, brain=pt, ghost=tmp_path / 'r.npz')
    head, frames = replay.read(tmp_path / 'g.jsonl.gz')
    shown = [f['tick'] for f in frames if 'ghosts' in f]
    # the next choice after the deposit at tick 30 starts it; SHOW seconds on it stops
    assert shown and 30 < shown[0] <= 32 and shown[-1] - shown[0] < SHOW * hz
    assert all(f['tick'] in shown for f in frames if shown[0] <= f['tick'] <= shown[-1])
    [ghost] = frames[shown[0]]['ghosts']
    nest = head['info']['nests'][0]
    assert ghost['id'] == frames[0]['creatures'][0]['id']
    # blank-ish notes put the tree where the intercept says, from the nest (the notes are not exactly zero)
    assert abs(ghost['x'] - nest['x']) < 10 and abs(ghost['y'] - nest['y']) < 10
    assert not any('ghosts' in f for f in frames[:30])


def test_nothing_without_a_deposit(tmp_path):
    pt = tmp_path / 'b.pt'
    readout(memory_brain(pt)).save(tmp_path / 'r.npz')
    record(TREE, tmp_path / 'g.jsonl.gz', 100, seed=1, brain=pt, ghost=tmp_path / 'r.npz')
    assert not any('ghosts' in f for f in replay.read(tmp_path / 'g.jsonl.gz')[1])


def test_a_readout_of_another_brain_is_refused(tmp_path):
    pt = tmp_path / 'b.pt'
    memory_brain(pt)
    readout('0' * 64).save(tmp_path / 'r.npz')
    with pytest.raises(ValueError, match='another brain'):
        record(TREE, tmp_path / 'g.jsonl.gz', 10, brain=pt, ghost=tmp_path / 'r.npz')
    with pytest.raises(ValueError, match='another brain'):
        record(TREE, tmp_path / 'g.jsonl.gz', 10, ghost=tmp_path / 'r.npz')


def test_an_apple_in_the_crop_ends_a_ghost():
    world = World(TREE, 1, 0)
    trail = Trail(readout(), world)
    trail.surface(np.ones((1, 1), bool), np.zeros((1, MEMORY)))
    assert len(trail.frame(0)) == 1
    world.crop[0, 0] = 1
    assert trail.frame(0) == []
    world.crop[0, 0] = 0
    assert trail.frame(0) == []
