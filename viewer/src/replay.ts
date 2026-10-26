// Reads replays written by the sim (sim/terrarium/replay.py): gzipped JSON lines,
// a header then one Frame per tick. Every viewer has to play every replay ever
// recorded, so this only ever learns new versions; it never drops old ones.
// Fields it doesn't know are ignored, since the format may gain them.

import {
  SIGNAL_COUNT, SIGNAL_OFF,
  type BlockState, type CreatureState, type EggState, type FlowerState, type FoodState, type Frame, type NestInfo, type StoreState, type WorldInfo,
} from './world';

export const REPLAY_FORMAT = 'terrarium-replay';
export const REPLAY_VERSION = 1;

export interface Replay {
  version: number;
  info: WorldInfo;
  // where it came from (commit, seed, config); shown, never relied on
  source: Record<string, unknown>;
  frames: Frame[];
}

export class ReplayError extends Error {}

type Obj = Record<string, unknown>;

export async function readReplay(bytes: Uint8Array<ArrayBuffer>): Promise<Replay> {
  const zipped = bytes[0] === 0x1f && bytes[1] === 0x8b;
  let text: string;
  try {
    text = zipped
      ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()
      : new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch (err) {
    throw new ReplayError(zipped ? `it's damaged and won't unzip (${String(err)})` : 'it isn\'t a text or gzip file');
  }
  return parseReplay(text);
}

export function parseReplay(text: string): Replay {
  const lines = text.split('\n');
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  if (!lines.length) throw new ReplayError('the file is empty');

  const head = parseLine(lines[0], 1);
  if (head.format !== REPLAY_FORMAT) throw new ReplayError('it isn\'t a Terrarium replay');
  const version = head.version;
  if (typeof version !== 'number' || !Number.isInteger(version) || version < 1) {
    throw new ReplayError(`line 1: version: expected a whole number, got ${JSON.stringify(version)}`);
  }
  if (version > REPLAY_VERSION) {
    throw new ReplayError(`it was written by a newer sim (format v${version}); this viewer reads up to v${REPLAY_VERSION}`);
  }

  const info = readInfo(obj(head.info, 'line 1: info'));
  const source = head.source === undefined ? {} : obj(head.source, 'line 1: source');
  const frames = lines.slice(1).map((line, i) => readFrame(parseLine(line, i + 2), `line ${i + 2}`));
  if (!frames.length) throw new ReplayError('it has a header but no frames');
  return { version, info, source, frames };
}

function parseLine(line: string, n: number): Obj {
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch {
    throw new ReplayError(`line ${n} isn't valid JSON`);
  }
  return obj(value, `line ${n}`);
}

function readInfo(o: Obj): WorldInfo {
  const where = 'line 1: info';
  return {
    width: num(o, 'width', where),
    height: num(o, 'height', where),
    tickHz: num(o, 'tickHz', where),
    maxSpeed: num(o, 'maxSpeed', where),
    nests: list(o, 'nests', where, (n, w): NestInfo => ({
      colony: int(n, 'colony', w), x: num(n, 'x', w), y: num(n, 'y', w), radius: num(n, 'radius', w),
    })),
  };
}

function readFrame(o: Obj, where: string): Frame {
  return {
    tick: int(o, 'tick', where),
    creatures: list(o, 'creatures', where, (c, w): CreatureState => {
      const signal = int(c, 'signal', w);
      if (signal < SIGNAL_OFF || signal >= SIGNAL_COUNT) throw new ReplayError(`${w}.signal: no signal ${signal}`);
      return {
        id: int(c, 'id', w), colony: int(c, 'colony', w), x: num(c, 'x', w), y: num(c, 'y', w),
        heading: num(c, 'heading', w), speed: num(c, 'speed', w), size: num(c, 'size', w),
        energy: num(c, 'energy', w), signal, carrying: c.carrying === undefined ? 0 : int(c, 'carrying', w),
        holding: c.holding === undefined ? 0 : int(c, 'holding', w),
        nectar: c.nectar === undefined ? 0 : num(c, 'nectar', w),
        sprinting: c.sprinting === undefined ? 0 : int(c, 'sprinting', w),
      };
    }),
    food: list(o, 'food', where, (f, w): FoodState => {
      if (f.kind !== 'common' && f.kind !== 'jelly') throw new ReplayError(`${w}.kind: unknown food ${JSON.stringify(f.kind)}`);
      return { id: int(f, 'id', w), kind: f.kind, x: num(f, 'x', w), y: num(f, 'y', w) };
    }),
    blocks: list(o, 'blocks', where, (b, w): BlockState => ({
      id: int(b, 'id', w), x: num(b, 'x', w), y: num(b, 'y', w), angle: num(b, 'angle', w), w: num(b, 'w', w), h: num(b, 'h', w),
    })),
    stores: o.stores === undefined ? [] : list(o, 'stores', where, (s, w): StoreState => ({ colony: int(s, 'colony', w), jelly: int(s, 'jelly', w) })),
    light: o.light === undefined ? 1 : num(o, 'light', where),
    eggs: o.eggs === undefined ? [] : list(o, 'eggs', where, (e, w): EggState => ({
      id: int(e, 'id', w), colony: int(e, 'colony', w), x: num(e, 'x', w), y: num(e, 'y', w), progress: num(e, 'progress', w),
    })),
    flowers: o.flowers === undefined ? [] : list(o, 'flowers', where, (f, w): FlowerState => ({ id: int(f, 'id', w), x: num(f, 'x', w), y: num(f, 'y', w) })),
  };
}

function obj(value: unknown, where: string): Obj {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new ReplayError(`${where}: expected an object`);
  return value as Obj;
}

function num(o: Obj, key: string, where: string): number {
  const v = o[key];
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new ReplayError(`${where}.${key}: expected a number, got ${JSON.stringify(v)}`);
  return v;
}

function int(o: Obj, key: string, where: string): number {
  const v = num(o, key, where);
  if (!Number.isInteger(v)) throw new ReplayError(`${where}.${key}: expected a whole number, got ${v}`);
  return v;
}

function list<T>(o: Obj, key: string, where: string, read: (item: Obj, where: string) => T): T[] {
  const v = o[key];
  if (!Array.isArray(v)) throw new ReplayError(`${where}.${key}: expected a list`);
  return v.map((item, i) => read(obj(item, `${where}.${key}[${i}]`), `${where}.${key}[${i}]`));
}
