// &preview: make-believe nectar flowers and sprints laid over an old replay, to
// judge how they look before the sim has them. Nothing here comes from a brain:
// flowers open at random by day (often near the first Terrikin, so the follow
// camera sees them), whoever walks into an open one drinks it, and anyone
// heading fast at one within sight is drawn sprinting.

import type { Frame, WorldInfo } from './world';

const LIFE = 15; // seconds a flower stays open
const BOOST = 8; // seconds a drink lasts
const REACH = 0.75;
const SEE = 7;

function rng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function withNectar(info: WorldInfo, step: () => Frame | null): () => Frame | null {
  const rand = rng(7);
  const hz = info.tickHz;
  const flowers: { id: number; x: number; y: number; born: number; nectar: number }[] = [];
  const boost = new Map<number, number>();
  let nextId = 1;
  let due = 4 * hz;

  function spot(frame: Frame) {
    const first = frame.creatures.find((c) => c.energy > 0);
    const half = Math.min(info.width, info.height) / 2 - 1.5;
    for (let i = 0; i < 30; i++) {
      let x: number;
      let y: number;
      if (first && rand() < 0.6) {
        const a = rand() * Math.PI * 2;
        const r = 2.5 + rand() * 3.5;
        [x, y] = [first.x + Math.cos(a) * r, first.y + Math.sin(a) * r];
      } else {
        [x, y] = [(rand() * 2 - 1) * half, (rand() * 2 - 1) * half];
      }
      if (Math.abs(x) > half || Math.abs(y) > half) continue;
      if (info.nests.every((n) => Math.hypot(x - n.x, y - n.y) > n.radius + 1.5)) return { x, y };
    }
    return null;
  }

  return () => {
    const frame = step();
    if (!frame) return null;
    const t = frame.tick;
    if (frame.light > 0.5 && t >= due) {
      const at = spot(frame);
      if (at) flowers.push({ id: nextId++, ...at, born: t, nectar: 1 });
      due = t + (8 + rand() * 8) * hz;
    }
    const creatures = frame.creatures.map((c) => {
      let sprinting = 0;
      if (c.energy > 0) {
        for (const f of flowers) {
          if (f.nectar <= 0) continue;
          const d = Math.hypot(f.x - c.x, f.y - c.y);
          if (d < REACH) {
            f.nectar = 0;
            boost.set(c.id, t + BOOST * hz);
          } else if (d < SEE && c.speed > 0.5 * info.maxSpeed) {
            const off = Math.atan2(f.y - c.y, f.x - c.x) - c.heading;
            if (Math.abs(Math.atan2(Math.sin(off), Math.cos(off))) < 0.5) sprinting = 1;
          }
        }
      }
      const nectar = c.energy > 0 ? Math.max(0, ((boost.get(c.id) ?? 0) - t) / hz) : 0;
      return { ...c, nectar, sprinting: nectar > 0 ? 1 : sprinting };
    });
    for (let i = flowers.length - 1; i >= 0; i--) {
      if (flowers[i].nectar <= 0 || t - flowers[i].born > LIFE * hz) flowers.splice(i, 1);
    }
    return { ...frame, creatures, flowers: flowers.map(({ id, x, y }) => ({ id, x, y })) };
  };
}
