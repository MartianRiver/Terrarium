import { describe, expect, it } from 'vitest';
import { Director } from '../src/director';
import type { CreatureState, Frame } from '../src/world';

function blob(id: number, x: number, y: number, extra: Partial<CreatureState> = {}): CreatureState {
  return { id, colony: 0, x, y, heading: 0, speed: 0, size: 1, energy: 1, signal: -1, carrying: 0, holding: 0,
    nectar: 0, sprinting: 0, load: 0, young: 1, stamina: 1, ...extra };
}

function frame(creatures: CreatureState[], food: Frame['food'] = []): Frame {
  return { tick: 0, creatures, food, blocks: [], stores: [], light: 1, eggs: [], flowers: [], flags: [] };
}

describe('the action camera', () => {
  it('leaves worlds that are not games to the usual follow', () => {
    expect(new Director().shot(frame([blob(1, 0, 0), blob(2, 3, 0)]), 0.1)).toBeNull();
  });

  it('in tag, watches whoever is it and the nearest one, from behind it', () => {
    const d = new Director();
    const shot = d.shot(frame([blob(1, 0, 0, { signal: 0 }), blob(2, 4, 0), blob(3, -9, 0)]), 0.1)!;
    expect(shot.x).toBeCloseTo(1.6);
    expect(shot.spread).toBeCloseTo(4);
    expect(shot.from).toBeCloseTo(0);
  });

  it('sticks with a pair until another is clearly closer, but follows a tag straight away', () => {
    const d = new Director();
    d.shot(frame([blob(1, 0, 0, { signal: 0 }), blob(2, 4, 0), blob(3, -9, 0)]), 0.1);
    // 3 comes a little closer than 2: not enough to cut away
    expect(d.shot(frame([blob(1, 0, 0, { signal: 0 }), blob(2, 4, 0), blob(3, -3.8, 0)]), 0.1)!.from).toBeCloseTo(0);
    // 2 is tagged: the camera goes with the new it at once
    const shot = d.shot(frame([blob(1, 0, 0), blob(2, 0.9, 0, { signal: 0 }), blob(3, -3.8, 0)]), 0.1)!;
    expect(shot.x).toBeCloseTo(0.9 * 0.6 + 0 * 0.4);
  });

  it('in hide-and-seek, watches the hiders during the count, then a seeker and its nearest hider', () => {
    const d = new Director();
    const counting = d.shot(frame([blob(1, -2, 5), blob(2, 2, 5), blob(3, 0, -5, { colony: 1, signal: 2 }), blob(4, 1, -5, { colony: 1, signal: 2 })]), 0.1)!;
    expect(counting.x).toBeCloseTo(0);
    expect(counting.y).toBeCloseTo(5);
    expect(counting.from).toBeNull();
    const after = d.shot(frame([blob(1, -2, 5), blob(2, 2, 5), blob(3, 0, -5, { colony: 1 }), blob(4, 2, 1, { colony: 1 })]), 0.1)!;
    expect(after.spread).toBeCloseTo(4);
    expect(after.from).toBeCloseTo(Math.PI / 2);
  });

  it('in peekaboo, watches the berry and whoever is nearest it', () => {
    const shot = new Director().shot(frame([blob(1, 0, 0), blob(2, 8, 8)], [{ id: 9, kind: 'common', x: 2, y: 0, hidden: true }]), 0.1)!;
    expect(shot.spread).toBeCloseTo(2);
    expect(shot.from).toBeCloseTo(0);
  });

  it('in capture the flag, follows the carrier and frames whoever could take it off them', () => {
    const d = new Director();
    const f = { ...frame([blob(1, 0, 0), blob(2, 6, 0, { colony: 1 }), blob(3, 2, 0, { colony: 1 })]),
      flags: [{ colony: 1, x: 0, y: 0, down: false, carrier: 1 }, { colony: 0, x: -8, y: 0, down: false, carrier: -1 }] };
    const shot = d.shot(f, 0.1)!;
    expect(d.lead).toBe(1);
    expect(shot.spread).toBeCloseTo(2);
  });
});
