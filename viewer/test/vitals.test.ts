import { describe, expect, it } from 'vitest';
import { bearing, hasCompass, holding, notesLabel, pointName, turnTo, vitalsAsk } from '../src/vitals';
import type { CreatureState, Frame, WorldInfo } from '../src/world';

const baby: CreatureState = { id: 3, colony: 0, x: 0, y: 0, heading: 0, speed: 0, size: 1, energy: 1, signal: -1, carrying: 0, holding: 0,
  nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1, dung: 0, z: 0 };

describe('the followed one’s card', () => {
  // three.js's default camera looks down -z, with +x to the right of the screen
  const ahead = { x: 0, z: -1 };

  it('points the way home from where the camera faces', () => {
    expect(turnTo(0, -5, ahead)).toBeCloseTo(0);
    expect(turnTo(5, 0, ahead)).toBeCloseTo(Math.PI / 2);
    expect(turnTo(-5, 0, ahead)).toBeCloseTo(-Math.PI / 2);
    expect(Math.abs(turnTo(0, 5, ahead))).toBeCloseTo(Math.PI);
    // camera turned to face +x: home along +x is straight up the screen, along +z to the right
    expect(turnTo(5, 0, { x: 1, z: 0 })).toBeCloseTo(0);
    expect(turnTo(0, 5, { x: 1, z: 0 })).toBeCloseTo(Math.PI / 2);
  });

  it('says what it carries, an apple only in the tree’s world', () => {
    expect(holding(baby, null, false)).toBe('');
    expect(holding({ ...baby, carrying: 1 }, null, true)).toBe('an apple, for home');
    expect(holding({ ...baby, carrying: 1 }, null, false)).toBe('food in its crop');
    expect(holding({ ...baby, dung: 1 }, null, false)).toBe('a dropping');
    const flag = { flags: [{ colony: 1, x: 0, y: 0, down: false, carrier: 3 }] } as unknown as Frame;
    expect(holding({ ...baby, load: 1 }, flag, false)).toBe('a flag');
  });

  it('reads the toggle from the url', () => {
    expect(vitalsAsk('')).toEqual({ force: null, big: false });
    expect(vitalsAsk('?replay=x&vitals=1')).toEqual({ force: true, big: false });
    expect(vitalsAsk('?vitals=big')).toEqual({ force: true, big: true });
    expect(vitalsAsk('?vitals=0')).toEqual({ force: false, big: false });
    expect(vitalsAsk('?vitals=off').force).toBe(false);
  });

  it('says whether the notes are kept or wiped', () => {
    expect(notesLabel({})).toBe('');
    expect(notesLabel({ brain: { id: 'abc' } })).toBe('');
    expect(notesLabel({ brain: { id: 'abc-wiped' } })).toBe('wiped each time it gets home');
    expect(notesLabel({ brain: { id: 'abc-wiped', notes: 'kept' } })).toBe('kept');
    expect(notesLabel({ brain: 'g1-7-wiped' })).toBe('wiped each time it gets home');
  });

  it('shows the compass in a tree world or one with [home] far', () => {
    const info = { tree: null } as WorldInfo;
    expect(hasCompass(info)).toBe(false);
    expect(hasCompass({ tree: 2 } as WorldInfo)).toBe(true);
    expect(hasCompass(info, { config: { home: { far: 12 } } })).toBe(true);
    expect(hasCompass(info, { config: { home: { far: 0 } } })).toBe(false);
  });

  it('reads a heading as a bearing from north (up the default view, -y)', () => {
    expect(bearing(-Math.PI / 2)).toBeCloseTo(0); // facing -y
    expect(bearing(0)).toBeCloseTo(Math.PI / 2); // +x is east
    expect(Math.abs(bearing(Math.PI / 2))).toBeCloseTo(Math.PI); // +y is south
    expect(pointName(0)).toBe('N');
    expect(pointName(Math.PI / 2)).toBe('E');
    expect(pointName(-Math.PI / 2)).toBe('W');
    expect(pointName(-Math.PI * 0.75)).toBe('SW');
    expect(pointName(Math.PI)).toBe('S');
  });
});
