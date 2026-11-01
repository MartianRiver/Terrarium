import { expect, test } from 'vitest';
import { fresh, opened, record, starsFor } from '../src/kidsprogress';

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
