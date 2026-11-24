import json
from dataclasses import replace

import numpy as np
import pytest
import torch

from terrarium import battery
from terrarium.battery_skills import cohort_alive, spells, survival
from terrarium.brain import SHAPE, Brain, save
from terrarium.config import DEFAULT, load
from terrarium.schema import ACTIONS
from terrarium.world import World

SEED = 8_121_000


@pytest.fixture
def tiny(tmp_path):
    """A small untrained brain with memory, in a run folder named the way a run's is."""
    torch.manual_seed(0)
    brain = Brain(**SHAPE).with_memory(8)
    folder = tmp_path / '20261111-095142-n70b-vision12-s1-40ae7fc221e6' / 'checkpoints'
    folder.mkdir(parents=True)
    save(brain, folder / '00000000100.pt', samples=100)
    return folder


def short(cfg):
    """The test world with a 20 s game, and a day and night that fit in it."""
    return replace(cfg, episode=replace(cfg.episode, seconds=20.0),
                   night=replace(cfg.night, cycle=20.0 if cfg.night.on else 0.0, length=8.0, dusk=2.0))


@pytest.mark.parametrize('skill', list(battery.SKILLS))
def test_each_test_runs_on_a_tiny_brain(skill, tiny):
    cfg = short(load(battery.CONFIGS / f'{skill}.toml'))
    r = battery.SKILLS[skill](cfg, next(tiny.glob('*.pt')), 2, SEED)
    assert 'na' in r or all(v is None or isinstance(v, (int, float, list, str)) for v in r.values())
    if skill != 'displace':
        assert 'na' not in r


def test_a_brain_is_found_from_its_run_and_named_from_the_folder(tiny):
    for spec in (tiny, tiny.parent, next(tiny.glob('*.pt'))):
        name, path = battery.find_brain(str(spec))
        assert path.name == '00000000100.pt'
    assert battery.find_brain(str(tiny.parent))[0] == 'n70b-vision12-s1'
    assert battery.find_brain(f'mine={tiny}')[0] == 'mine'


def test_spells_are_the_runs_of_true_in_each_column():
    mask = np.array([[1, 0], [1, 1], [0, 1], [1, 1], [1, 0]], bool)
    assert sorted(spells(mask)) == [2.0, 2.0, 3.0]
    assert len(spells(np.zeros((4, 2, 2), bool))) == 0


def test_main_prints_a_line_and_writes_the_numbers(tiny, tmp_path, monkeypatch, capsys):
    out = tmp_path / 'b.json'
    monkeypatch.setattr('sys.argv', ['battery', str(tiny), '--games', '2', '--seed', str(SEED), '--only', 'graze,night',
                                     '--world', f'night={battery.CONFIGS / "pond.toml"}', '--out', str(out)])
    battery.main()
    line = capsys.readouterr().out
    assert line.startswith('n70b-vision12-s1') and 'graze anchored' in line and 'n/a (the world has no nights)' in line
    doc = json.loads(out.read_text())
    mine = doc['brains']['n70b-vision12-s1@100']
    assert doc['seed'] == SEED and set(mine) == {'run', 'samples', 'id', 'checkpoint', 'graze', 'night'}
    assert mine['run'] == 'n70b-vision12-s1' and mine['samples'] == 100 and len(mine['id']) == 12


def test_two_checkpoints_of_one_run_are_both_kept(tiny, tmp_path, monkeypatch, capsys):
    save(Brain(**SHAPE).with_memory(8), tiny / '00000000200.pt', samples=200)
    save(Brain(**SHAPE).with_memory(8), tiny / '00000000100.pt', samples=100)
    out = tmp_path / 'b.json'
    args = [str(tiny / '00000000100.pt'), str(tiny / '00000000200.pt')]
    monkeypatch.setattr('sys.argv', ['battery', *args, '--games', '1', '--seed', str(SEED), '--only', 'graze', '--out', str(out)])
    battery.main()
    doc = json.loads(out.read_text())
    assert set(doc['brains']) == {'n70b-vision12-s1@100', 'n70b-vision12-s1@200'}
    assert doc['brains']['n70b-vision12-s1@200']['run'] == 'n70b-vision12-s1'
    assert [x.split()[0] for x in capsys.readouterr().out.splitlines()] == list(doc['brains'])
    monkeypatch.setattr('sys.argv', ['battery', args[0], args[0], '--games', '1', '--seed', str(SEED), '--only', 'graze'])
    with pytest.raises(SystemExit, match='twice'):
        battery.main()


def test_an_empty_checkpoint_folder_says_so(tmp_path):
    (tmp_path / 'checkpoints').mkdir()
    with pytest.raises(SystemExit, match='no checkpoint in'):
        battery.find_brain(str(tmp_path))


def test_apples_are_counted_apart_from_the_berries_beside_them():
    main = load(DEFAULT.parent / 'main-world.toml')
    w = World(main, 1, seed=6)
    w.energy[:] = 1.0
    w.fat[:] = main.fat.capacity
    w.food_regrow[:, main.tree.apples:w.wild] = 10_000

    def step(**yes):
        out = np.zeros((1, len(w.colony), len(ACTIONS)))
        out[..., 2:] = -1
        for name, on in yes.items():
            out[..., ACTIONS.index(name)] = 1.0 if on else -1.0
        w.step(out)

    # an apple is a meal and an apple taken
    w.physics.revive([0], [1], np.array([w.food_pos[0, 0]]))
    for _ in range(40):
        step(jump=w.z[0, 1] == 0)
        if w.crop[0, 1]:
            break
    assert w.apples_taken[0, 1] == 1 and w.meals[0, 1] == 1
    # a berry off the ground is a meal and no apple (a full nim carries it)
    w.food_regrow[0, main.tree.apples] = 0
    w.physics.revive([0], [0], np.array([w.food_pos[0, main.tree.apples]]))
    step()
    assert w.meals[0, 0] == 1 and w.apples_taken[0, 0] == 0 and w.crop[0, 0] == 1
    # home with a berry and an apple: stored counts both, apples_stored the apple
    w.physics.revive([0, 0], [0, 1], np.array([w.nests[0], w.nests[0]]))
    in_crop = w.crop[0, :2].tolist()
    step(unload=True)
    assert in_crop == [1, w.apples_taken[0, 1]] and w.stored[0, :2].tolist() == in_crop
    assert w.apples_stored[0, :2].tolist() == [0, w.apples_taken[0, 1]]


def test_cohort_survival_leaves_out_hatchlings_and_spare_places():
    cfg = load(DEFAULT.parent / 'main-world.toml')
    w = World(cfg, 2, seed=1)
    size, slots = cfg.colonies.size, cfg.colonies.slots
    assert cohort_alive(w).sum() == 2 * 2 * size
    # in game 0, one of colony 0's nims dies and a hatchling takes its place, and a spare place fills in colony 1
    w.alive[0, 0] = False
    w.alive[0, 0] = True
    w.creature_id[0, 0] = 99
    w.alive[0, slots + size] = True
    # in game 1, colony 1 is wiped out
    w.alive[1, slots:] = False
    r = survival(w)
    assert r['cohort'] == 2 * size
    assert r['alive'] == pytest.approx((2 * (2 * size) - 1 - size) / (2 * 2 * size), abs=1e-3)
    assert r['living'] == pytest.approx((2 * size + 1 + size) / 2, abs=0.01)
    assert r['colonies_alive'] == 0.75


def test_the_pond_test_says_who_never_reached_it_and_what_they_drank(tiny):
    cfg = short(load(battery.CONFIGS / 'pond.toml'))
    r = battery.SKILLS['pond'](cfg, next(tiny.glob('*.pt')), 2, SEED)
    assert 0 <= r['never_pond'] <= 1 and 0 <= r['thirst_deaths'] <= 1 and r['water_game'] >= 0
    assert (r['water_visit'] is None) == (r['visits'] == 0)
