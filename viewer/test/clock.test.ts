import { expect, test } from 'vitest';
import { clock } from '../src/clock';

test('the clock runs on from minutes to hours to days', () => {
  expect(clock(39.9)).toBe('0:39');
  expect(clock(3599)).toBe('59:59');
  expect(clock(3600)).toBe('1:00:00');
  expect(clock(86399)).toBe('23:59:59');
  expect(clock(2 * 86400 + 3 * 3600 + 15 * 60 + 9)).toBe('2d 03:15:09');
});
