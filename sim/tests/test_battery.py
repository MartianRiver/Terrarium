import json
from dataclasses import replace

import numpy as np
import pytest
import torch

from terrarium import battery
from terrarium.battery_skills import spells
from terrarium.brain import SHAPE, Brain, save
from terrarium.config import load

SEED = 8_121_000


@pytest.fixture
def tiny(tmp_path):
    """A small untrained brain with memory, in a run folder named the way a run's is."""
    torch.manual_seed(0)
    brain = Brain(**SHAPE).with_memory(8)
    folder = tmp_path / '20261111-095142-n70b-vision12-s1-40ae7fc221e6' / 'checkpoints'
    folder.mkdir(parents=True)
    save(brain, folder / '00000000100.pt')
    return folder


def short(cfg):
    """The test world with a 20 s game, and a day and night that fit in it."""
    return replace(cfg, episode=replace(cfg.episode, seconds=20.0),
                   night=replace(cfg.night, cycle=20.0 if cfg.night.on else 0.0, length=8.0, dusk=2.0))


@pytest.mark.parametrize('skill', list(battery.SKILLS))
def test_each_test_runs_on_a_tiny_brain(skill, tiny):
    cfg = short(load(battery.CONFIGS / f'{skill}.toml'))
    r = battery.SKILLS[skill](cfg, next(tiny.glob('*.pt')), 2, SEED)
    assert 'na' in r or all(v is None or isinstance(v, (int, float, list)) for v in r.values())
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
    assert doc['seed'] == SEED and set(doc['brains']['n70b-vision12-s1']) == {'checkpoint', 'graze', 'night'}
