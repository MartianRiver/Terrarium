// Every sample replay in the repo has to keep loading, and in CI so does one the
// sim has just written (REPLAY=path).

import { readdirSync, readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { describe, expect, test } from 'vitest';
import { REPLAY_VERSION, ReplayError, parseReplay, readReplay } from '../src/replay';

const SAMPLES = new URL('../../samples/', import.meta.url);

const header = { format: 'terrarium-replay', version: 1, info: { width: 26, height: 26, tickHz: 20, maxSpeed: 2.4, nests: [] } };
const frame = {
  tick: 0,
  creatures: [{ id: 1, colony: 0, x: 1, y: 2, heading: 0, speed: 0, size: 1, energy: 0.8, signal: -1 }],
  food: [{ id: 2, kind: 'common', x: 3, y: 4 }],
  blocks: [{ id: 3, x: 0, y: 0, angle: 0, w: 1, h: 1 }],
};
const lines = (...objs: unknown[]) => objs.map((o) => JSON.stringify(o)).join('\n') + '\n';
const bytes = (b: Uint8Array) => new Uint8Array(b);

async function check(path: string | URL) {
  const replay = await readReplay(bytes(readFileSync(path)));
  expect(replay.frames.length).toBeGreaterThan(0);
  expect(replay.info.nests.length).toBeGreaterThan(0);
  const ticks = replay.frames.map((f) => f.tick);
  expect(ticks).toEqual(ticks.map((_, i) => ticks[0] + i));
}

describe('sample replays', () => {
  const samples = readdirSync(SAMPLES).filter((f) => f.endsWith('.jsonl.gz'));

  test('there is at least one', () => expect(samples.length).toBeGreaterThan(0));
  test.each(samples)('%s loads', (name) => check(new URL(name, SAMPLES)));
  test.runIf(!!process.env.REPLAY)('a replay the sim just wrote loads', () => check(process.env.REPLAY!));
});

describe('reading', () => {
  const refuses = (text: string, message: RegExp) => expect(() => parseReplay(text)).toThrow(message);

  test('gzipped and plain text read the same', async () => {
    const text = lines(header, frame, { ...frame, tick: 1 });
    const plain = await readReplay(new TextEncoder().encode(text));
    const zipped = await readReplay(bytes(gzipSync(text)));
    expect(zipped).toEqual(plain);
    expect(plain.frames[1].creatures[0]).toEqual({ ...frame.creatures[0], carrying: 0 });
  });

  test('carrying and stores are read when there, and empty in replays from before them', () => {
    const later = { ...frame, creatures: [{ ...frame.creatures[0], carrying: 2 }], stores: [{ colony: 0, jelly: 5 }] };
    const replay = parseReplay(lines(header, frame, later));
    expect(replay.frames[0].stores).toEqual([]);
    expect(replay.frames[1].creatures[0].carrying).toBe(2);
    expect(replay.frames[1].stores).toEqual([{ colony: 0, jelly: 5 }]);
    refuses(lines(header, { ...later, stores: [{ colony: 0, jelly: 0.5 }] }), /jelly: expected a whole number/);
  });

  test('the light is read when there, and full day in worlds without nights', () => {
    const replay = parseReplay(lines(header, frame, { ...frame, light: 0.25 }));
    expect(replay.frames.map((f) => f.light)).toEqual([1, 0.25]);
    refuses(lines(header, { ...frame, light: 'dusk' }), /light/);
  });

  test('fields it doesn\'t know are ignored', () => {
    const replay = parseReplay(lines({ ...header, later: 1 }, { ...frame, weather: 'rain', creatures: [{ ...frame.creatures[0], mood: 2 }] }));
    expect(replay.frames[0].creatures[0]).toEqual({ ...frame.creatures[0], carrying: 0 });
  });

  test('refuses a newer format, saying so', () => {
    refuses(lines({ ...header, version: REPLAY_VERSION + 1 }, frame), /newer sim/);
  });

  test('refuses things that aren\'t replays', () => {
    refuses('', /empty/);
    refuses(lines({ ...header, format: 'something-else' }, frame), /isn't a Terrarium replay/);
    refuses('not json\n', /line 1 isn't valid JSON/);
    refuses(lines(header), /no frames/);
  });

  test('names the line and field that\'s wrong', () => {
    const bad = { ...frame, creatures: [{ ...frame.creatures[0], x: 'left' }] };
    refuses(lines(header, frame, bad), /line 3\.creatures\[0\]\.x: expected a number/);
    refuses(lines(header, { ...frame, food: [{ ...frame.food[0], kind: 'cake' }] }), /unknown food "cake"/);
    refuses(lines(header, { ...frame, creatures: [{ ...frame.creatures[0], signal: 9 }] }), /no signal 9/);
    refuses(lines(header, { ...frame, tick: 0.5 }), /tick: expected a whole number/);
  });

  test('a damaged gzip file is an error, not a crash', async () => {
    const zipped = bytes(gzipSync(lines(header, frame))).slice(0, 30);
    await expect(readReplay(zipped)).rejects.toBeInstanceOf(ReplayError);
  });
});
