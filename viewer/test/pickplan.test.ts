import { describe, expect, it } from 'vitest';
import { linePlan } from '../src/lines';
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
        'tree-04': stage(4, '18 m', { status: 'planned', pass: 'it beats the picker.', now: 'Growing the garden.' }),
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
    const cards = plan(trees, null, NOW).find((s) => s.key === 'earlier')!.cards;
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
    expect(tree.stages[3].pass).toBe('it beats the picker.');
    expect(tree.now).toBe('Growing the garden.');
    expect(plan(trees, null, NOW + 13 * 3600_000).find((s) => s.key === 'earlier')!.cards
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

// cut from the channel's index of 8 Nov: the colonies and nights lines, one question made to be asking now
const FILE = '0014-the-needs-reward-lifts-the-night-brains.md';
const f14 = { number: '0014', title: 'The needs reward is the one change that lifts the night brains', status: 'held-out', file: FILE };
const f15 = { number: '0015', title: 'A scripted nim lives through both nights', status: 'confirmed', file: '0015-a-scripted-nim-lives-through-both-nights.md' };
const f19 = { number: '0019', title: 'Starting at nightfall does not keep them in', status: 'held-out' };
const lined = (name: string, line: string, question: string, status: string, more = {}) =>
  game(name, { family: name, line, question, status, asking: false, answer: [], seen_in: [], training: false, goal: `Goal of ${line}.`, ...more });

const lineChannel: Channel = {
  updated: '2026-11-08T13:25:27+11:00',
  games: {
    'nights-a': lined('Nights', 'nights', 'Does 8M more lift it?', 'answered', { started: '2026-11-07T04:52:43+11:00', answer: [f14], seen_in: [f15, f19] }),
    'nights-b': lined('Nights', 'nights', 'Does 8M more lift it?', 'answered', { started: '2026-11-07T04:55:00+11:00', answer: [f14] }),
    'nights-c': lined('Nights', 'nights', 'Does a pay at dawn help?', 'asking', { started: '2026-11-08T11:28:07+11:00', asking: true, training: true, now: 'Latest: 0019 Dawn pay' }),
    'colonies-a': lined('Colonies', 'colonies', 'Does a fresh brain beat the 0.3 brain?', 'done', { started: '2026-10-31T02:30:53+11:00', result: '7.24 of 8 places, the 0.3 brain 6.29 (one seed of two).' }),
    'colonies-b': lined('Colonies', 'colonies', 'Do three colonies cost each other?', 'answered', { started: '2026-11-07T23:26:33+11:00', answer: [{ ...f14, number: '0016', title: 'Three colonies of six', file: '0016-x.md' }] }),
    old: game('Tag', { kind: 'a chasing game', training: false, finished: '2026-10-28T10:00:00+11:00' }),
    'tree-01': game('The apple tree', { family: 'The apple tree', nursery: 'tree', order: 1, status: 'done' }),
  },
  items: [
    { replay: 'a1.jsonl.gz', title: 'Nights · n47-a · seed 1 · 8.0M samples', game: 'nights-a' },
    { replay: 'a2.jsonl.gz', title: 'Nights · n47-a · seed 2 · 8.0M samples', game: 'nights-a' },
    { replay: 'b1.jsonl.gz', title: 'Nights · n47-b · seed 1 · 8.0M samples', game: 'nights-b' },
    { replay: 'c1.jsonl.gz', title: 'Nights · n47-dawn · seed 1 · 2.0M samples so far', game: 'nights-c' },
    { replay: 'ca.jsonl.gz', title: 'Colonies · cy-fresh · seed 1 · 64.0M samples', game: 'colonies-a' },
    { replay: 'cb.jsonl.gz', title: 'Colonies · cy-three · seed 1 · 8.0M samples', game: 'colonies-b' },
    { replay: 't.jsonl.gz', title: 'Tag', game: 'old' },
    { replay: 'tr.jsonl.gz', title: 'The apple tree · stage 1', game: 'tree-01' },
  ],
};

describe('lines of work', () => {
  const l = linePlan(lineChannel, NOW);

  it('asking now holds each line with something asking: its goal, the question and its live runs', () => {
    expect(l.asking.map((c) => [c.title, c.goal, c.questions.map((q) => q.text)])).toEqual([['Nights', 'Goal of nights.', ['Does a pay at dawn help?']]]);
    const q = l.asking[0].questions[0];
    expect(q.status).toBe('asking');
    expect(q.runs.map((r) => [r.title, r.note, r.live])).toEqual([['n47-dawn', 'seed 1 · 2.0M samples so far', true]]);
    expect(q.runs[0].href).toContain('&game=nights-c&start=c1.jsonl.gz');
  });

  it('is empty, not missing, when nothing is asking, and with no lines at all', () => {
    const quiet = linePlan({ ...lineChannel, games: { ...lineChannel.games, 'nights-c': { ...lineChannel.games!['nights-c'], asking: false, status: 'answered', training: false } } }, NOW);
    expect(quiet.asking).toEqual([]);
    expect(quiet.cards).toHaveLength(2);
    expect(linePlan(null, NOW)).toEqual({ asking: [], answered: [], more: 0, cards: [] });
    expect(linePlan({ updated: '', games: { old: lineChannel.games!.old }, items: [] }, NOW).cards).toEqual([]);
  });

  it('puts answered questions newest first, one question for the games that ask the same, answer from the finding’s file', () => {
    expect(l.answered.map((q) => q.text)).toEqual(['Do three colonies cost each other?', 'Does 8M more lift it?']);
    const more = l.answered[1];
    expect(more.runs.map((r) => r.title)).toEqual(['n47-a', 'n47-a', 'n47-b']);
    expect(more.answers.map((a) => [a.number, a.exact, a.href])).toEqual([
      ['0014', true, `https://github.com/MartianRiver/Terrarium/blob/next/docs/findings/${FILE}`],
    ]);
    expect(more.href).toContain('&game=nights-a,nights-b');
    expect(more.note).toMatch(/^answered · /);
  });

  it('keeps findings that only mention the runs as "also in", and links the findings list when the index has no file name', () => {
    const more = l.answered[1];
    expect(more.seen.map((c) => [c.number, c.exact])).toEqual([['0015', true], ['0019', false]]);
    expect(more.seen[1].href).toBe('https://github.com/MartianRiver/Terrarium/blob/next/docs/findings/README.md');
    const dup = linePlan({ ...lineChannel, games: { x: lined('X', 'x', 'q?', 'answered', { answer: [f14], seen_in: [f14, f15] }) }, items: [] }, NOW);
    expect(dup.answered[0].seen.map((c) => c.number)).toEqual(['0015']);
  });

  it('shows a finished question with no finding by its numbers, and counts a few answers before "show all"', () => {
    const colonies = l.cards.find((c) => c.key === 'colonies')!;
    const done = colonies.questions.find((q) => q.status === 'done')!;
    expect([done.answers, done.result]).toEqual([[], '7.24 of 8 places, the 0.3 brain 6.29 (one seed of two).']);
    expect(l.answered).not.toContain(done);
    const games: Channel['games'] = {};
    for (let i = 0; i < 9; i++) games![`q${i}`] = lined('Q', 'q', `Question ${i}?`, 'answered', { started: new Date(NOW - i * 3600_000).toISOString(), answer: [f14] });
    const many = linePlan({ updated: '', games, items: [] }, NOW);
    expect([many.answered.length, many.more, many.answered[0].text]).toEqual([9, 3, 'Question 0?']);
  });

  it('gives each line a card: asking lines first, questions newest first, and the line’s own latest note', () => {
    expect(l.cards.map((c) => [c.key, c.count])).toEqual([['nights', '2 questions · 1 answered · 1 asking now'], ['colonies', '2 questions · 1 answered']]);
    expect(l.cards[0].asking).toBe(true);
    expect(l.cards[0].questions.map((q) => q.text)).toEqual(['Does a pay at dawn help?', 'Does 8M more lift it?']);
    expect(l.cards[0].now).toBe('Latest: 0019 Dawn pay');
  });

  it('leaves games without a line to the old lists, and folds the old nurseries into an archive', () => {
    const sections = plan(lineChannel, null, NOW);
    const titles = sections.flatMap((s) => s.cards.map((c) => c.title));
    expect(titles).toContain('Tag');
    expect(titles).toContain('The apple tree');
    expect(titles.some((t) => /Nights|Colonies/.test(t))).toBe(false);
    expect(sections.find((s) => s.key === 'earlier')!.cards.map((c) => c.title)).toEqual(['The apple tree']);
    expect(sections.find((s) => s.key === 'nursery')!.cards.map((c) => c.title)).toEqual(['Tag']);
    expect(sections[0].cards).toEqual([]);
  });
});
