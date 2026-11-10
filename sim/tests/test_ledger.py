from dataclasses import replace
from pathlib import Path

import pytest

from terrarium import ledger
from terrarium.config import load, load_train

DATA = Path(__file__).parent / 'data'
WORLD = load(DATA / 'night-world.toml')
TRAIN = load_train(DATA / 'night-train.toml')


def codes(world=WORLD, train=TRAIN):
    return [w['code'] for w in ledger.build(world, train)['warnings']]


def test_the_night_recipe_pays_delivery_through_the_tree_and_not_twice():
    data = ledger.build(WORLD, TRAIN)
    sources = [x['source'] for x in data['rows']]
    assert 'game.tree' in sources and 'reward.stored' not in sources
    assert 'double-pay' not in codes()
    text = next(w['text'] for w in data['warnings'] if w['code'] == 'paid-elsewhere' and 'delivery' in w['text'])
    assert '[tree] points' in text


def test_stored_on_top_of_the_tree_warns_double_pay():
    train = replace(TRAIN, reward=replace(TRAIN.reward, stored=0.5))
    assert 'double-pay' in codes(train=train)


def test_a_night_that_falls_after_the_game_ends_is_never_trained():
    world = replace(WORLD, night=replace(WORLD.night, cycle=240.0, length=40.0))
    assert 'never-dark' in codes(world)
    staggered = replace(TRAIN, start=replace(TRAIN.start, staggered=True))
    assert 'never-dark' not in codes(world, staggered)
    assert 'never-dark' not in codes()


def test_horizon_numbers():
    hz = ledger.build(WORLD, TRAIN)['horizon']
    assert hz['step_s'] == pytest.approx(0.2)
    assert hz['efold_s'] == pytest.approx(19.9, abs=0.05)
    assert hz['gae_efold_s'] == pytest.approx(9.9, abs=0.05)
    assert hz['weights'][30] == pytest.approx(0.99 ** 150)
    assert hz['rollout_s'] == pytest.approx(25.6)


def test_a_payoff_past_two_efolds_warns_and_death_at_zero_does_too():
    assert 'delay' in codes()
    train = replace(TRAIN, reward=replace(TRAIN.reward, death=0.0))
    assert 'death-zero' in codes(train=train)


def test_needs_and_needs_lost_unequal_is_turnover():
    train = replace(TRAIN, reward=replace(TRAIN.reward, needs_lost=0.5))
    assert 'turnover' in codes(train=train) and 'turnover' not in codes()


def test_a_new_reward_term_or_play_hook_is_never_skipped():
    assert ledger.uncovered(TRAIN.reward, WORLD) == []
    assert ledger.uncovered(TRAIN.reward, WORLD, 'play += w.tree.points(w.alive)\nplay += w.lanterns.points(w.alive)') == [
        'game hook w.lanterns pays through play']
    # a hook whose game is off in this world isn't a payoff of it
    assert ledger.uncovered(TRAIN.reward, WORLD, 'play += w.water.points(w.alive)') == []


def test_every_source_finds_its_line_in_the_step():
    assert all(ledger.line_of(s.anchor) for s in ledger.REGISTRY)


def test_every_reward_term_has_a_source():
    import dataclasses
    from terrarium.config import Reward
    keys = {s.key for s in ledger.REGISTRY}
    assert {f'reward.{f.name}' for f in dataclasses.fields(Reward) if f.name != 'colony'} <= keys


def test_the_table_and_json_render():
    data = ledger.build(WORLD, TRAIN)
    text = ledger.render(data, ('w', 't'))
    assert '| source | when it pays | who gets it | size | delay / weight |' in text and '## Warnings' in text
