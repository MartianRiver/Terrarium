import pytest

from terrarium import seeds

LEDGER = '''# comment
[[block]]
start = 8_100_000
size = 1000
use = "confirm"
what = "first"
where = "x"
date = 2026-11-06

[[block]]
start = 8_101_000
size = 256
use = "test"
what = "second"
where = "x"
date = 2026-11-06
'''


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / 'seeds.toml'
    path.write_text(LEDGER)
    return path


def test_take_skips_taken_blocks(ledger):
    assert seeds.take('confirm', 'third', 'findings/0099', ledger) == 8_102_000
    assert seeds.take('confirm', 'fourth', 'findings/0099', ledger) == 8_103_000
    blocks = seeds.parse(ledger.read_text())
    assert [b['start'] for b in blocks][-2:] == [8_102_000, 8_103_000]
    assert blocks[-1]['what'] == 'fourth' and blocks[-1]['size'] == 1000
    assert not seeds.problems(blocks)
    assert ledger.read_text().startswith('# comment')


def test_take_rounds_up_past_a_short_block(tmp_path):
    path = tmp_path / 'seeds.toml'
    path.write_text(LEDGER.replace('size = 1000', 'size = 300'))
    assert seeds.take('confirm', 'x', 'y', path) == 8_102_000


def test_scratch_has_its_own_range(ledger):
    assert seeds.take('scratch', 'a', 'b', ledger) == 9_300_000
    assert seeds.take('scratch', 'a', 'b', ledger) == 9_301_000
    assert seeds.take('confirm', 'a', 'b', ledger) == 8_102_000


def test_take_works_on_a_missing_file_and_without_a_final_newline(tmp_path):
    path = tmp_path / 'new.toml'
    assert seeds.take('confirm', 'a', 'b', path) == 8_100_000
    path.write_text(path.read_text().rstrip('\n'))
    assert seeds.take('confirm', 'c', 'd', path) == 8_101_000
    assert len(seeds.parse(path.read_text())) == 2


def test_take_refuses_empty_words_and_a_broken_ledger(ledger):
    with pytest.raises(SystemExit):
        seeds.take('confirm', '  ', 'x', ledger)
    ledger.write_text(LEDGER + '\n[[block]]\nstart = 8_100_500\nsize = 10\nuse = "confirm"\n'
                               'what = "a"\nwhere = "b"\ndate = 2026-11-06\n')
    with pytest.raises(SystemExit):
        seeds.take('confirm', 'a', 'b', ledger)


def test_overlap_and_check_range():
    blocks = seeds.parse(LEDGER)
    assert seeds.overlap(blocks, 8_100_999, 1)['what'] == 'first'
    assert seeds.overlap(blocks, 8_099_000, 1000) is None
    assert seeds.overlap(blocks, 8_099_000, 1001)['what'] == 'first'
    assert seeds.overlap(blocks, 8_101_256, 5) is None
    assert seeds.number('8,113,000') == 8_113_000


def test_problems():
    assert seeds.problems(seeds.parse(LEDGER)) == []
    bad = seeds.parse('[[block]]\nstart = 1\nsize = 5\nuse = "other"\nwhat = "a"\nwhere = "b"\ndate = 2026-11-06\n'
                      '[[block]]\nstart = 2\nsize = 5\n')
    assert any('use is "other"' in p for p in seeds.problems(bad))
    assert any('missing' in p for p in seeds.problems(bad))


def test_the_real_ledger_is_clean():
    blocks = seeds.parse(seeds.LEDGER.read_text())
    assert seeds.problems(blocks) == []
    assert seeds.overlap(blocks, 8_113_000, 256)['where'] == 'findings/0016'
