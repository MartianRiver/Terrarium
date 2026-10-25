import { expect, test } from 'vitest';
import { nearestPoint } from '../src/grips';

test('a grip reaches the nearest point on a turned block', () => {
  const door = { x: 2.85, y: 0, angle: 0, w: 0.5, h: 1.5 };
  expect(nearestPoint({ x: 3.6, y: 0.2 }, door)).toEqual({ x: 3.1, y: 0.2 });
  const turned = nearestPoint({ x: 0, y: 2 }, { x: 0, y: 0, angle: Math.PI / 2, w: 2, h: 0.5 });
  expect(turned.x).toBeCloseTo(0);
  expect(turned.y).toBeCloseTo(1);
});
