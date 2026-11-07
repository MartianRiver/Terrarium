// What there is to hear in each new frame: the same events reel/sound.py finds in a replay (a bite, peekaboo's
// hidden berry found, a tag, a sprint starting, a death, a hatch, a first sip of nectar, jelly unloaded at a nest),
// worked out from one frame to the next so they work on anything that makes frames. Keep the two in step.

import type { Frame, NestInfo } from './world';

export type CueKind = 'bite' | 'found' | 'tag' | 'sprint' | 'death' | 'hatch' | 'nectar' | 'unload';

export interface Cue {
  kind: CueKind;
  x: number;
  y: number;
}

const IT = 0; // the it's signal in tag
const NEAR = 1.0; // squared metres: food gone this close to a live Terrikin was bitten
const TOUCH = 1.44; // squared: the bulb moving this short a way is a tag (tagpop.ts)

export class Cues {
  private food = new Map<number, { x: number; y: number }>();
  private hidden = new Set<number>();
  private energy = new Map<number, number>();
  private sprint = new Map<number, number>();
  private nectar = new Map<number, number>();
  private eggs = new Map<number, { x: number; y: number }>();
  private stores = new Map<number, number>();
  private it: number | null = null;
  private nests = new Map<number, NestInfo>();
  private fresh = true;

  // a new episode: nothing carries over, and the first frame after this is heard as the start, not as changes
  reset(nests: NestInfo[]) {
    this.nests = new Map(nests.map((n) => [n.colony, n]));
    this.food.clear();
    this.hidden.clear();
    this.energy.clear();
    this.sprint.clear();
    this.nectar.clear();
    this.eggs.clear();
    this.stores.clear();
    this.it = null;
    this.fresh = true;
  }

  next(f: Frame): Cue[] {
    const out: Cue[] = [];
    const alive = f.creatures.filter((c) => c.energy > 0);
    const food = new Map(f.food.map((x) => [x.id, { x: x.x, y: x.y }]));
    for (const [id, p] of this.food) {
      if (food.has(id) || !alive.some((c) => (c.x - p.x) ** 2 + (c.y - p.y) ** 2 < NEAR)) continue;
      out.push({ kind: this.hidden.has(id) ? 'found' : 'bite', ...p });
    }
    this.food = food;
    this.hidden = new Set(f.food.filter((x) => x.hidden).map((x) => x.id));

    const it = f.creatures.find((c) => c.signal === IT);
    const was = this.it === null ? undefined : f.creatures.find((c) => c.id === this.it);
    if (it && was && it.id !== was.id && (it.x - was.x) ** 2 + (it.y - was.y) ** 2 < TOUCH) {
      out.push({ kind: 'tag', x: (it.x + was.x) / 2, y: (it.y + was.y) / 2 });
    }
    this.it = it ? it.id : null;

    for (const c of f.creatures) {
      if (c.sprinting && !this.sprint.get(c.id)) out.push({ kind: 'sprint', x: c.x, y: c.y });
      this.sprint.set(c.id, c.sprinting);
      if ((this.energy.get(c.id) ?? 0) > 0 && c.energy <= 0) out.push({ kind: 'death', x: c.x, y: c.y });
      this.energy.set(c.id, c.energy);
      if (c.nectar > 0 && (this.nectar.get(c.id) ?? 0) <= 0) out.push({ kind: 'nectar', x: c.x, y: c.y });
      this.nectar.set(c.id, c.nectar);
    }

    // an egg gone with its id walking about has hatched
    const eggs = new Map(f.eggs.map((e) => [e.id, { x: e.x, y: e.y }]));
    const ids = new Set(alive.map((c) => c.id));
    for (const [id, p] of this.eggs) if (!eggs.has(id) && ids.has(id)) out.push({ kind: 'hatch', ...p });
    this.eggs = eggs;

    for (const s of f.stores) {
      const nest = this.nests.get(s.colony);
      if (nest && s.jelly > (this.stores.get(s.colony) ?? s.jelly)) out.push({ kind: 'unload', x: nest.x, y: nest.y });
      this.stores.set(s.colony, s.jelly);
    }
    // whoever starts out sprinting or sipping isn't news
    if (this.fresh) {
      this.fresh = false;
      return [];
    }
    return out;
  }
}
