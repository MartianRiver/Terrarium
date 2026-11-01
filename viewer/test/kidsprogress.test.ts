import { expect, test } from 'vitest';
import { fresh, load, opened, record, starsFor } from '../src/kidsprogress';

const TARGETS: [number, number] = [8, 14];

test('a catch is a star, the targets two and three', () => {
  expect([0, 1, 7, 8, 13, 14, 40].map((n) => starsFor(n, TARGETS))).toEqual([0, 1, 1, 2, 2, 3, 3]);
});

test('two stars on a level open the next, once, and never past the last', () => {
  let p = fresh();
  expect(opened(p, 'big', 3)).toBe(1);
  let round;
  [p, round] = record(p, 'big', 1, 3, 5, TARGETS);
  expect(round.opened).toBeNull();
  expect(opened(p, 'big', 3)).toBe(1);
  [p, round] = record(p, 'big', 1, 3, 9, TARGETS);
  expect(round.opened).toBe(2);
  [p, round] = record(p, 'big', 1, 3, 20, TARGETS);
  expect(round.opened).toBeNull();
  [p, round] = record(p, 'big', 2, 3, 9, TARGETS);
  [p, round] = record(p, 'big', 3, 3, 30, TARGETS);
  expect(opened(p, 'big', 3)).toBe(3);
  expect(round.opened).toBeNull();
});

test('a worse round keeps the best and the stars already earned', () => {
  let p = fresh();
  let round;
  [p, round] = record(p, 'little', 1, 1, 15, [10, 20]);
  expect(round).toMatchObject({ stars: 2, best: 15, record: true });
  [p, round] = record(p, 'little', 1, 1, 3, [10, 20]);
  expect(round).toMatchObject({ stars: 1, best: 15, record: false });
  expect(p.stars['little:1']).toBe(2);
  expect(p.total).toBe(18);
  expect(p.rounds).toBe(2);
});

test('levels of other games are their own', () => {
  let [p] = record(fresh(), 'little', 1, 1, 30, [10, 20]);
  expect(opened(p, 'big', 5)).toBe(1);
  [p] = record(p, 'big', 1, 5, 0, TARGETS);
  expect(p.stars['big:1']).toBe(0);
});

test('a costume or colour this page no longer has comes back as a blue Terrikin, the rest kept', () => {
  const stored = new Map<string, string>();
  stored.set('terrarium.kids.progress', JSON.stringify({ ...fresh(), total: 9, look: 'unicorn', colour: 0 }));
  const was = globalThis.localStorage;
  globalThis.localStorage = { getItem: (k: string) => stored.get(k) ?? null } as Storage;
  try {
    expect(load()).toMatchObject({ total: 9, look: 'terrikin', colour: 1 });
    stored.set('terrarium.kids.progress', JSON.stringify({ ...fresh(), look: 'dino', colour: 3 }));
    expect(load()).toMatchObject({ look: 'dino', colour: 3 });
  } finally {
    globalThis.localStorage = was;
  }
});
