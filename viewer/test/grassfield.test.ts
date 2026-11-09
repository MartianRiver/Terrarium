import { describe, expect, test } from 'vitest';
import { paint } from '../src/grassfield';

describe('the grass field', () => {
  test('cover lands on the texture the way the sim\'s grid lies: x across, y up from the bottom row', () => {
    // 2 × 2, bytes ix * 2 + iy: (0,0)=10 (0,1)=20 (1,0)=30 (1,1)=40
    const data = new Uint8Array(2 * 2 * 4);
    expect(paint(data, Buffer.from([10, 20, 30, 40]).toString('base64'), 2, 1)).toBe(true);
    const alpha = [0, 1, 2, 3].map((i) => data[i * 4 + 3]);
    // the far side of the arena (iy = 1) is the first row of the texture
    expect(alpha).toEqual([20, 40, 10, 30]);
  });

  test('a cover that isn\'t the grid\'s size changes nothing', () => {
    const data = new Uint8Array(4 * 4).fill(7);
    expect(paint(data, Buffer.from([1, 2, 3]).toString('base64'), 2)).toBe(false);
    expect(data.every((v) => v === 7)).toBe(true);
  });

  test('a full cell still lets a little of the ground through', () => {
    const data = new Uint8Array(4);
    paint(data, Buffer.from([255]).toString('base64'), 1);
    expect(data[3]).toBeGreaterThan(200);
    expect(data[3]).toBeLessThan(255);
  });
});
