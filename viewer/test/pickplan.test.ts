import { describe, expect, it } from 'vitest';
import { plan, type Channel } from '../src/pickplan';

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

  it('with an older index that doesn’t say what’s training, goes by how fresh it is', () => {
    const old = { ...channel, games: { peek: game('Peekaboo') }, items: [channel.items[2]] };
    expect(plan(old, null, NOW)[0].cards).toHaveLength(1);
    expect(plan(old, null, NOW + 3600_000)[0].cards).toHaveLength(0);
  });
});
