// The viewer hears what reel/sound.py hears: the counts below are sound.py's events() on each sample replay.

import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';
import { Cues, type CueKind } from '../src/cues';
import { readReplay } from '../src/replay';
import type { CreatureState, Frame } from '../src/world';

const SAMPLES = new URL('../../samples/', import.meta.url);

const FROM_SOUND_PY: Record<string, Partial<Record<CueKind, number>>> = {
  '0.1-random': { bite: 15 },
  '0.2-forager': { bite: 51 },
  '0.3-colonies': { bite: 145, unload: 22, nectar: 2, death: 4, hatch: 4 },
};

describe('cues in the sample replays', () => {
  for (const [name, want] of Object.entries(FROM_SOUND_PY)) {
    test(name, async () => {
      const replay = await readReplay(new Uint8Array(readFileSync(new URL(`${name}.jsonl.gz`, SAMPLES))));
      const cues = new Cues();
      cues.reset(replay.info.nests);
      const got: Partial<Record<CueKind, number>> = {};
      for (const f of replay.frames) for (const c of cues.next(f)) got[c.kind] = (got[c.kind] ?? 0) + 1;
      expect(got).toEqual(want);
    });
  }
});

const blob = (id: number, x: number, y: number, more: Partial<CreatureState> = {}): CreatureState => ({
  id, colony: 0, x, y, heading: 0, speed: 0, size: 1, energy: 0.8, signal: -1,
  carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1, dung: 0, ...more,
});
const frame = (tick: number, creatures: CreatureState[], food: Frame['food'] = []): Frame =>
  ({ tick, creatures, food, blocks: [], stores: [], light: 1, eggs: [], flowers: [], flags: [] });
const berry = (id: number, x: number, y: number, hidden = false) => ({ id, kind: 'common', x, y, hidden }) as Frame['food'][number];

describe('cues', () => {
  test('a tag is the bulb moving to a Terrikin it touched, not one far off', () => {
    const cues = new Cues();
    cues.reset([]);
    cues.next(frame(0, [blob(1, 0, 0, { signal: 0 }), blob(2, 1, 0), blob(3, 9, 9)]));
    expect(cues.next(frame(1, [blob(1, 0, 0), blob(2, 1, 0, { signal: 0 }), blob(3, 9, 9)]))).toEqual([{ kind: 'tag', x: 0.5, y: 0 }]);
    expect(cues.next(frame(2, [blob(1, 0, 0), blob(2, 1, 0), blob(3, 9, 9, { signal: 0 })]))).toEqual([]);
  });

  test("peekaboo's hidden berry is found, a berry in sight is bitten, one gone from nowhere near is neither", () => {
    const cues = new Cues();
    cues.reset([]);
    cues.next(frame(0, [blob(1, 0, 0)], [berry(5, 0.5, 0, true), berry(6, 0, 0.5), berry(7, 8, 8)]));
    expect(cues.next(frame(1, [blob(1, 0, 0)], [])).map((c) => c.kind)).toEqual(['found', 'bite']);
  });

  test('the first frame after a reset is quiet, whoever is already sprinting', () => {
    const cues = new Cues();
    cues.reset([]);
    expect(cues.next(frame(0, [blob(1, 0, 0, { sprinting: 1, nectar: 3 })]))).toEqual([]);
    expect(cues.next(frame(1, [blob(1, 0, 0, { sprinting: 1, nectar: 3 })]))).toEqual([]);
    expect(cues.next(frame(2, [blob(2, 0, 0, { sprinting: 1 })])).map((c) => c.kind)).toEqual(['sprint']);
  });
});
