// Reads a mind track (sim/terrarium/mind.py): one Terrikin's brain through the episode a replay plays, a line each
// time it chose. Local only: the runs server records one on request, for the brain window (mindpanel.ts).

import type { Frame } from './world';

export const MIND_FORMAT = 'terrarium-mind';
export const MIND_VERSION = 1;
// further apart than this (metres) and the replay isn't the episode the mind was played in
export const DRIFT = 0.05;

export interface MindHeader {
  creature: number;
  seed: number;
  brain: {
    id: string; file: string; repeat: number; yes_no: string;
    shape: { width: number; layers: number; heads: number };
    schema: { self: string[]; ray: string[]; kinds: string[]; actions: string[] };
  };
  // angles: each ray's angle off the heading (older tracks don't have it: rays were spread evenly)
  rays: { count: number; fov: number; range: number; angles?: number[] };
  tickHz: number;
}

export interface Thought {
  tick: number;
  x: number;
  y: number;
  self: number[];
  kinds: number[];
  // ray lengths as a share of the range, and whether what it hit is a nestmate
  dist: number[];
  nestmate: number[];
  // [layer][head][token]: its own token's attention over itself (0) and each ray (1..)
  attention: number[][][];
  // [stage][unit]: its own token's units as it enters and after each layer
  units: number[][];
  summary: number[];
  value: number;
  mean: number[];
  odds: (number | null)[];
  action: number[];
}

export class MindError extends Error {}

export class MindTrack {
  constructor(readonly head: MindHeader, readonly thoughts: Thought[]) {}

  // what it was thinking at a tick: the last choice it made at or before it
  at(tick: number): Thought | null {
    let lo = 0, hi = this.thoughts.length - 1, best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (this.thoughts[mid].tick <= tick) [best, lo] = [mid, mid + 1];
      else hi = mid - 1;
    }
    return best < 0 ? null : this.thoughts[best];
  }

  // the first tick where the replay has the Terrikin somewhere else than the mind does, or null if they agree
  partsFrom(frames: Frame[]): number | null {
    const byTick = new Map(frames.map((f) => [f.tick, f]));
    for (const t of this.thoughts) {
      const c = byTick.get(t.tick)?.creatures.find((c) => c.id === this.head.creature);
      if (c && Math.hypot(c.x - t.x, c.y - t.y) > DRIFT) return t.tick;
    }
    return null;
  }
}

export async function readMind(bytes: Uint8Array<ArrayBuffer>): Promise<MindTrack> {
  let text: string;
  try {
    text = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
  } catch (err) {
    throw new MindError(`it won't unzip (${String(err)})`);
  }
  return parseMind(text);
}

export function parseMind(text: string): MindTrack {
  const lines = text.split('\n').filter((l) => l.trim());
  let head: MindHeader & { format?: string; version?: number };
  try {
    head = JSON.parse(lines[0]);
  } catch {
    throw new MindError('its first line isn\'t JSON');
  }
  if (head.format !== MIND_FORMAT) throw new MindError('it isn\'t a mind track');
  if (head.version !== MIND_VERSION) throw new MindError(`it's version ${head.version}, and this viewer reads ${MIND_VERSION}`);
  const thoughts = lines.slice(1).map((l, i) => {
    const t = JSON.parse(l) as Thought;
    if (t.self?.length !== head.brain.schema.self.length || t.kinds?.length !== head.rays.count) {
      throw new MindError(`line ${i + 2} doesn't fit its header`);
    }
    return t;
  });
  return new MindTrack(head, thoughts);
}
