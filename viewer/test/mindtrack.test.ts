import { describe, expect, it } from 'vitest';
import { MindError, parseMind } from '../src/mindtrack';
import type { Frame } from '../src/world';

const head = {
  format: 'terrarium-mind', version: 1, creature: 7, seed: 0, tickHz: 20,
  brain: { id: 'x', file: 'b.pt', repeat: 2, yes_no: 'gaussian', shape: { width: 4, layers: 1, heads: 1 },
    schema: { self: ['energy'], ray: ['distance'], kinds: ['nothing', 'food'], actions: ['thrust'] } },
  rays: { count: 2, fov: 3, range: 8 },
};

const thought = (tick: number, x: number) => ({
  tick, x, y: 0, self: [1], kinds: [0, 1], dist: [1, 0.5], nestmate: [0, 0], attention: [[[0.5, 0.25, 0.25]]], units: [[0, 0, 0, 0], [0, 0, 0, 0]],
  summary: [0, 0, 0, 0], value: 1, mean: [0.5], odds: [null], action: [0.5],
});

const text = (...lines: object[]) => lines.map((l) => JSON.stringify(l)).join('\n');

function frame(tick: number, x: number): Frame {
  return { tick, creatures: [{ id: 7, colony: 0, x, y: 0, heading: 0, speed: 0, size: 1, energy: 1, signal: -1, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0 }],
    food: [], blocks: [], stores: [], light: 1, flowers: [], eggs: [] };
}

describe('mind tracks', () => {
  it('give the last thought at or before a tick', () => {
    const mind = parseMind(text(head, thought(0, 0), thought(2, 1), thought(4, 2)));
    expect(mind.at(-1)).toBeNull();
    expect(mind.at(0)!.tick).toBe(0);
    expect(mind.at(3)!.tick).toBe(2);
    expect(mind.at(99)!.tick).toBe(4);
  });

  it('say where a replay parts from the episode they were played in', () => {
    const mind = parseMind(text(head, thought(0, 0), thought(2, 1), thought(4, 2)));
    expect(mind.partsFrom([frame(0, 0), frame(2, 1.01), frame(4, 2)])).toBeNull();
    expect(mind.partsFrom([frame(0, 0), frame(2, 1), frame(4, 2.5)])).toBe(4);
  });

  it('refuse what isn\'t one, or doesn\'t fit its header', () => {
    expect(() => parseMind(text({ ...head, format: 'terrarium-replay' }))).toThrow(MindError);
    expect(() => parseMind(text({ ...head, version: 2 }))).toThrow(/version 2/);
    expect(() => parseMind(text(head, { ...thought(0, 0), kinds: [0] }))).toThrow(/line 2/);
  });
});
