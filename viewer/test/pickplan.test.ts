import { describe, expect, it } from 'vitest';
import { plan, when, type Channel } from '../src/pickplan';

const NOW = Date.parse('2026-11-01T21:00:00+11:00');
const game = (name: string, more = {}) => ({ name, kind: 'a memory game', goal: 'Find the berry.', setup: 'A berry. Then more.', ...more });

const channel: Channel = {
  updated: '2026-11-01T20:50:00+11:00',
  games: {
    half: game('Peekaboo, half speed', { family: 'Peekaboo', variant: 'half speed', training: true, question: 'Can it remember?', about: 'Slower babies.' }),
    peek: game('Peekaboo', { family: 'Peekaboo', training: false, result: 'Finds 85%.' }),
    hold: game('Tidy up', { kind: 'a tidying game', variant: 'picking up takes a moment', training: false, finished: '2026-11-01T20:21:04+11:00' }),
    old: game('Tag', { kind: 'a chasing game', training: false, finished: '2026-10-28T10:00:00+11:00' }),
    colony: game('Young colonies', { kind: 'the main world', training: false }),
  },
  items: [
    { replay: 'h1.jsonl.gz', title: 'Peekaboo, half speed · window 25.6 s · seed 1 · 9.8M samples so far', game: 'half' },
    { replay: 'h2.jsonl.gz', title: 'Peekaboo, half speed · window 12.8 s · seed 1 · 8.2M samples so far', game: 'half' },
    { replay: 'p.jsonl.gz', title: 'Peekaboo · memory', game: 'peek' },
    { replay: 't.jsonl.gz', title: 'Tidy up · picking up takes a moment · seed 1 · 8.0M samples', game: 'hold' },
    { replay: 'g.jsonl.gz', title: 'Tag', game: 'old' },
    { replay: 'c.jsonl.gz', title: 'Young colonies', game: 'colony' },
  ],
};

describe('the picker', () => {
  const sections = plan(channel, null, NOW);
  const live = sections[0];

  it('puts what’s training first, then what finished in the last two days, and nothing older', () => {
    expect(live.cards.map((c) => c.title)).toEqual(['Peekaboo: half speed', 'Tidy up: picking up takes a moment']);
    expect(live.cards[0].note).toBe('training now');
    expect(live.cards[1].note).toMatch(/^finished /);
    expect(live.cards[1].rows).toEqual([]);
    expect(live.cards[1].href).toContain('&start=t.jsonl.gz');
  });

  it('gives each run of a line its own link, named by its arm', () => {
    const rows = live.cards[0].rows;
    expect(rows.map((r) => [r.title, r.note])).toEqual([['window 25.6 s', 'seed 1 · 9.8M samples so far'], ['window 12.8 s', 'seed 1 · 8.2M samples so far']]);
    expect(rows[0].href).toContain('&start=h1.jsonl.gz');
  });

  it('lists a family once with its question, and never names a setup the same as its family', () => {
    const nursery = sections.find((s) => s.key === 'nursery')!;
    const peekaboo = nursery.cards.find((c) => c.title === 'Peekaboo')!;
    expect(peekaboo.text).toBe('Can it remember?');
    expect(peekaboo.live).toBe(true);
    expect(peekaboo.rows.map((r) => r.title)).toEqual(['half speed', 'A berry.']);
    expect(peekaboo.rows[1].text).toBe('Finds 85%.');
    expect(nursery.cards[0]).toBe(peekaboo);
  });

  it('keeps the main world with the colonies', () => {
    expect(sections.find((s) => s.key === 'colonies')!.cards.map((c) => c.title)).toEqual(['Young colonies']);
  });

  it('folds a nursery into its stages in order: checkpoints to watch, earlier brains, and what’s still to come', () => {
    const stage = (order: number, variant: string, more = {}) =>
      game('The apple tree', { kind: 'a jumping game', family: 'The apple tree', nursery: 'tree', order, variant, ...more });
    const trees: Channel = {
      updated: channel.updated,
      games: {
        'tree-04': stage(4, '18 m', { status: 'planned' }),
        'tree-01': stage(1, 'apples just out of reach', { status: 'done', finished: '2026-11-01T20:00:00+11:00' }),
        'tree-03': stage(3, '16 m', { status: 'held' }),
        'tree-02': stage(2, '14 m', { status: 'training', training: true }),
        'needs-01': game('Needs', { family: 'Needs', nursery: 'needs', order: 1, variant: 'hungry babies', status: 'planned' }),
      },
      items: [
        { replay: 'a.jsonl.gz', title: 'The apple tree · apples just out of reach · seed 1 · 4.2M samples', game: 'tree-01', samples: 4.2e6, took: '2.4 days of play, learned in 9 min on the Mac',
          stages: [{ label: 'random moves', replay: 'a-r.jsonl.gz' }, { label: 'now · 4.2M', replay: 'a.jsonl.gz' }] },
        { replay: 'b.jsonl.gz', title: 'The apple tree · 14 m · seed 1 · 2.0M samples so far', game: 'tree-02', earlier: [{ label: 'apples just out of reach', replay: 'b-was-a.jsonl.gz' }] },
        { replay: 'c.jsonl.gz', title: 'The apple tree · 16 m · seed 1 · 1.0M samples so far', game: 'tree-03' },
      ],
    };
    const cards = plan(trees, null, NOW).find((s) => s.key === 'nursery')!.cards;
    const tree = cards.find((c) => c.title === 'The apple tree')!.nursery!;
    expect(tree.stages.map((s) => [s.order, s.title, s.status, s.note])).toEqual([
      [1, 'apples just out of reach', 'done', `finished ${when('2026-11-01T20:00:00+11:00', NOW)}`],
      [2, '14 m', 'training', 'training now'],
      [3, '16 m', 'held', 'on hold'],
      [4, '18 m', 'planned', 'not yet in training'],
    ]);
    expect(tree.status).toBe('training');
    expect(tree.count).toBe('4 stages · 1 training · 1 on hold · 1 to come');
    expect(tree.stages[0].took).toBe('4.2M samples: 2.4 days of play, learned in 9 min on the Mac');
    expect(tree.stages[0].chips.map((c) => c.label)).toEqual(['random moves', 'now · 4.2M']);
    expect(tree.stages[0].chips[0].href).toContain('&start=a.jsonl.gz&at=a-r.jsonl.gz');
    expect(tree.stages[1].earlier[0].href).toContain('&at=b-was-a.jsonl.gz');
    expect(tree.stages[3].chips).toEqual([]);
    expect(tree.stages.map((s) => s.recent)).toEqual([true, false, false, false]);
    expect(plan(trees, null, NOW + 13 * 3600_000).find((s) => s.key === 'nursery')!.cards
      .find((c) => c.title === 'The apple tree')!.nursery!.stages[0].recent).toBe(false);
    const needs = cards.find((c) => c.title === 'Needs')!;
    expect(needs.href).toBe('');
    expect(needs.nursery!.status).toBe('planned');
  });

  it('tops the list with everything training, then only the newest finished, six in all', () => {
    const games: Channel['games'] = { half: channel.games!.half };
    const items = [channel.items[0]];
    for (let i = 0; i < 8; i++) {
      games[`f${i}`] = game(`Done ${i}`, { training: false, finished: new Date(NOW - (i + 1) * 3600_000).toISOString() });
      items.push({ replay: `f${i}.jsonl.gz`, title: `Done ${i}`, game: `f${i}` });
    }
    const top = plan({ updated: channel.updated, games, items }, null, NOW)[0].cards;
    expect(top.map((c) => c.title)).toEqual(['Peekaboo: half speed', 'Done 0: A berry.', 'Done 1: A berry.', 'Done 2: A berry.', 'Done 3: A berry.', 'Done 4: A berry.']);
  });

  it('with an older index that doesn’t say what’s training, goes by how fresh it is', () => {
    const old = { ...channel, games: { peek: game('Peekaboo') }, items: [channel.items[2]] };
    expect(plan(old, null, NOW)[0].cards).toHaveLength(1);
    expect(plan(old, null, NOW + 3600_000)[0].cards).toHaveLength(0);
  });
});
