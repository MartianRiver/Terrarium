# The ledger of seed blocks, docs/seeds.toml: every range used for anything that decides.
# A score only checks anything if nothing was chosen by the seeds it uses, so a block is
# taken here before it's used, and the file says who has it.
#
#   python -m terrarium.seeds take --use confirm --what "..." --where "findings/0021"
#   python -m terrarium.seeds list
#   python -m terrarium.seeds check 8,113,000 --episodes 256

import argparse
import fcntl
import json
import tomllib
from datetime import date
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent.parent / 'docs' / 'seeds.toml'

USES = ('choosing', 'confirm', 'scratch', 'test')
KEYS = ('start', 'size', 'use', 'what', 'where', 'date')
# confirms and tests share the range from 8,100,000; scratch has its own so it never eats a confirm block
FLOOR = {'confirm': 8_100_000, 'test': 8_100_000, 'scratch': 9_300_000}
BLOCK = 1000


def parse(text: str) -> list[dict]:
    return tomllib.loads(text).get('block', [])


def problems(blocks: list[dict]) -> list[str]:
    out = []
    for i, b in enumerate(blocks, 1):
        missing = [k for k in KEYS if k not in b]
        if missing:
            out.append(f'block {i}: missing {", ".join(missing)}')
        elif b['use'] not in USES:
            out.append(f'block {i}: use is "{b["use"]}", not one of {", ".join(USES)}')
        elif not (isinstance(b['start'], int) and isinstance(b['size'], int) and b['size'] > 0):
            out.append(f'block {i}: start and size must be whole numbers, size above 0')
    if out:
        return out
    ordered = sorted(blocks, key=lambda b: b['start'])
    for a, b in zip(ordered, ordered[1:]):
        if a['start'] + a['size'] > b['start']:
            out.append(f'{a["start"]:,} (size {a["size"]}) overlaps {b["start"]:,}')
    return out


def overlap(blocks: list[dict], start: int, size: int) -> dict | None:
    for b in sorted(blocks, key=lambda b: b['start']):
        if start < b['start'] + b['size'] and b['start'] < start + size:
            return b
    return None


def next_free(blocks: list[dict], use: str, size: int = BLOCK) -> int:
    start = FLOOR[use]
    while hit := overlap(blocks, start, size):
        start = -(-(hit['start'] + hit['size']) // BLOCK) * BLOCK
    return start


def entry(start: int, size: int, use: str, what: str, where: str) -> str:
    q = lambda s: json.dumps(s, ensure_ascii=False)
    return (f'[[block]]\nstart = {start:_}\nsize = {size}\nuse = {q(use)}\n'
            f'what = {q(what)}\nwhere = {q(where)}\ndate = {date.today().isoformat()}\n')


def take(use: str, what: str, where: str, path: Path = LEDGER) -> int:
    if not what.strip() or not where.strip():
        raise SystemExit('say what the block is for (--what) and where it will be written up (--where)')
    # one lock across the read and the append, so two sessions taking at once get different blocks
    with open(path, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        text = f.read()
        blocks = parse(text)
        bad = problems(blocks)
        if bad:
            raise SystemExit(f'{path.name} has problems, fix them first: {"; ".join(bad)}')
        start = next_free(blocks, use)
        if text and not text.endswith('\n'):
            f.write('\n')
        f.write(('\n' if text else '') + entry(start, BLOCK, use, what.strip(), where.strip()))
    return start


def table(blocks: list[dict]) -> str:
    rows = [f'{b["start"]:>10,}  {b["size"]:>5}  {b["use"]:<8}  {b["date"]}  {b["what"]}  [{b["where"]}]'
            for b in sorted(blocks, key=lambda b: b['start'])]
    return '\n'.join([f'{"start":>10}  {"size":>5}  {"use":<8}  {"date":<10}  what  [where]', *rows])


def number(s: str) -> int:
    return int(s.replace(',', '').replace('_', ''))


def main():
    parser = argparse.ArgumentParser(description='The ledger of seed blocks, docs/seeds.toml.',
                                     epilog='Seeds may be written with commas: check 8,113,000 --episodes 256')
    sub = parser.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('take', help='take the next free block of 1,000 seeds; prints its first seed alone')
    t.add_argument('--use', choices=sorted(FLOOR), required=True,
                   help='confirm and test count up from 8,100,000, scratch from 9,300,000')
    t.add_argument('--what', required=True, help='a short plain sentence on what it is for')
    t.add_argument('--where', required=True, help='finding number, notes file or lab folder')
    sub.add_parser('list', help='every block in the ledger')
    c = sub.add_parser('check', help='exit 0 and say "free" if the seeds are in no block, else exit 1 and name it')
    c.add_argument('seed', type=number)
    c.add_argument('--episodes', type=int, default=1, help='games from the seed up (default 1)')
    args = parser.parse_args()

    if args.cmd == 'take':
        print(take(args.use, args.what, args.where))
    elif args.cmd == 'list':
        print(table(parse(LEDGER.read_text())))
    else:
        hit = overlap(parse(LEDGER.read_text()), args.seed, max(args.episodes, 1))
        if hit:
            raise SystemExit(f'taken: {hit["start"]:,} to {hit["start"] + hit["size"] - 1:,} '
                             f'({hit["use"]}: {hit["what"]}, {hit["where"]})')
        print('free')


if __name__ == '__main__':
    main()
