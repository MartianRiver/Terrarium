import tomllib

import pytest

from terrarium.config import DEFAULT, Config, ConfigError, build, load


def raw():
    with open(DEFAULT, 'rb') as f:
        return tomllib.load(f)


def test_default_loads_and_round_trips():
    cfg = load()
    assert len(cfg.block) == 2
    assert build(Config, cfg.to_dict()) == cfg


def test_unknown_key_is_refused():
    data = raw()
    data['creature']['legs'] = 4
    with pytest.raises(ConfigError, match=r'config\.creature: unknown key\(s\) legs'):
        build(Config, data)


def test_missing_key_is_refused():
    data = raw()
    del data['food']['radius']
    with pytest.raises(ConfigError, match=r'config\.food: missing key\(s\) radius'):
        build(Config, data)


def test_wrong_type_is_refused():
    data = raw()
    data['colonies']['size'] = 6.5
    with pytest.raises(ConfigError, match=r'config\.colonies\.size: expected int'):
        build(Config, data)
    data = raw()
    data['block'][1]['mass'] = True
    with pytest.raises(ConfigError, match=r'config\.block\[1\]\.mass'):
        build(Config, data)


def test_int_is_fine_for_a_float():
    data = raw()
    data['arena']['size'] = 30
    cfg = build(Config, data)
    assert cfg.arena.size == 30.0 and isinstance(cfg.arena.size, float)
