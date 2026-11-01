// Stage 0 stand-in for the sim: scripted wandering, eating and block shoving.
// It emits the same Frame shape real replays will, so the renderer never knows
// the difference. Throwaway once stage 1 lands.

import { createLogger } from './lib/logger';
import {
  SIGNAL_COUNT, SIGNAL_OFF,
  type BlockState, type CreatureState, type FoodState, type Frame, type NestInfo, type WorldInfo,
} from './world';

const log = createLogger('demo');

const TICK_HZ = 20;
const DT = 1 / TICK_HZ;
const MAP = 26;
const COLONIES = 3;
const PER_COLONY = 6;
const COMMON_FOOD = 28;
const MAX_SPEED = 2.4;
const RADIUS = 0.45;
const TURN_RATE = 3.5;
const HOME_RANGE = 9;

type Goal = 'wander' | 'idle' | 'food' | 'block';

interface Agent extends CreatureState {
  goal: Goal;
  goalTicks: number;
  drift: number;
  targetBlock: number;
  signalTicks: number;
}

// Seeded so the demo plays the same way every load
function makeRng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const wrapAngle = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));

export function createDemo(seed = 7) {
  const rng = makeRng(seed);
  const half = MAP / 2;
  let tick = 0;
  let nextId = 1;

  const nests: NestInfo[] = [];
  for (let c = 0; c < COLONIES; c++) {
    const a = (c / COLONIES) * Math.PI * 2 + Math.PI / 2;
    nests.push({ colony: c, x: Math.cos(a) * half * 0.68, y: Math.sin(a) * half * 0.68, radius: 1.6 });
  }

  const agents: Agent[] = [];
  for (const nest of nests) {
    for (let i = 0; i < PER_COLONY; i++) {
      const a = rng() * Math.PI * 2;
      agents.push({
        id: nextId++, colony: nest.colony,
        x: nest.x + Math.cos(a) * 2.5, y: nest.y + Math.sin(a) * 2.5,
        heading: rng() * Math.PI * 2, speed: 0, size: 1,
        energy: 0.5 + rng() * 0.5, signal: SIGNAL_OFF, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1, dung: 0,
        goal: 'wander', goalTicks: Math.floor(rng() * 60), drift: 0, targetBlock: 0, signalTicks: 0,
      });
    }
  }

  const randomGroundPoint = () => {
    for (;;) {
      const x = (rng() - 0.5) * (MAP - 3);
      const y = (rng() - 0.5) * (MAP - 3);
      if (nests.every((n) => Math.hypot(n.x - x, n.y - y) > n.radius + 1.5)) return { x, y };
    }
  };

  const food: FoodState[] = [];
  for (let i = 0; i < COMMON_FOOD; i++) food.push({ id: nextId++, kind: 'common', hidden: false, ...randomGroundPoint() });
  let regrow: number[] = [];

  const blocks: BlockState[] = [
    { id: nextId++, x: 3.5, y: 3, angle: 0, w: 1.3, h: 1.3, carried: 0 },
    { id: nextId++, x: -4, y: -3.5, angle: 0, w: 2.4, h: 1.1, carried: 0 },
  ];
  // share of overlap the block absorbs when shoved: lighter blocks move more
  const give = new Map([[blocks[0].id, 0.5], [blocks[1].id, 0.2]]);

  log.info('demo world created', { agents: agents.length, food: food.length, blocks: blocks.length, seed });

  function pickGoal(a: Agent) {
    const r = rng();
    if (a.energy < 0.55) a.goal = 'food';
    else if (r < 0.15) {
      a.goal = 'block';
      a.targetBlock = blocks[Math.floor(rng() * blocks.length)].id;
    } else if (r < 0.35) a.goal = 'idle';
    else a.goal = 'wander';
    a.goalTicks = Math.floor((2 + rng() * 5) * TICK_HZ);
  }

  function steer(a: Agent) {
    let desired = a.heading;
    let targetSpeed = 0;
    const nest = nests[a.colony];

    if (a.goal === 'food') {
      let best: FoodState | undefined;
      let bestD = Infinity;
      for (const f of food) {
        const d = Math.hypot(f.x - a.x, f.y - a.y);
        if (f.kind === 'common' && d < bestD) { best = f; bestD = d; }
      }
      if (best) desired = Math.atan2(best.y - a.y, best.x - a.x);
      targetSpeed = MAX_SPEED * 0.9;
    } else if (a.goal === 'block') {
      const b = blocks.find((b) => b.id === a.targetBlock)!;
      desired = Math.atan2(b.y - a.y, b.x - a.x);
      targetSpeed = MAX_SPEED * 0.5;
    } else if (a.goal === 'wander') {
      a.drift = a.drift * 0.92 + (rng() - 0.5) * 0.5;
      desired = a.heading + a.drift;
      if (Math.hypot(nest.x - a.x, nest.y - a.y) > HOME_RANGE) desired = Math.atan2(nest.y - a.y, nest.x - a.x);
      targetSpeed = MAX_SPEED * 0.45;
    } else {
      // idle: look around a bit
      if (rng() < 0.03) a.drift = (rng() - 0.5) * 2.5;
      desired = a.heading + a.drift * 0.2;
    }

    // turn back from the edges
    const edge = half - 2;
    if (Math.abs(a.x) > edge || Math.abs(a.y) > edge) desired = Math.atan2(-a.y, -a.x);

    const delta = clamp(wrapAngle(desired - a.heading), -TURN_RATE * DT, TURN_RATE * DT);
    a.heading = wrapAngle(a.heading + delta);
    a.speed += (targetSpeed - a.speed) * 0.15;
  }

  function flash(a: Agent, signal: number, seconds: number) {
    a.signal = signal;
    a.signalTicks = Math.floor(seconds * TICK_HZ);
  }

  function eat(a: Agent) {
    const i = food.findIndex((f) => f.kind === 'common' && Math.hypot(f.x - a.x, f.y - a.y) < RADIUS + 0.3);
    if (i < 0) return;
    const [f] = food.splice(i, 1);
    a.energy = Math.min(1, a.energy + 0.4);
    flash(a, 0, 1);
    if (a.energy > 0.9) pickGoal(a);
    regrow.push(tick + Math.floor((6 + rng() * 6) * TICK_HZ));
    log.debug('food eaten', { creature: a.id, food: f.id, energy: +a.energy.toFixed(2) });
  }

  function separate() {
    for (let i = 0; i < agents.length; i++) {
      for (let j = i + 1; j < agents.length; j++) {
        const a = agents[i], b = agents[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.hypot(dx, dy);
        const overlap = RADIUS * 2 - d;
        if (overlap <= 0 || d < 1e-6) continue;
        const nx = dx / d, ny = dy / d;
        a.x -= nx * overlap * 0.5; a.y -= ny * overlap * 0.5;
        b.x += nx * overlap * 0.5; b.y += ny * overlap * 0.5;
      }
    }
  }

  // circle vs axis-aligned box; overlap is split between creature and block
  function shoveBlocks(a: Agent) {
    for (const b of blocks) {
      const cx = clamp(a.x, b.x - b.w / 2, b.x + b.w / 2);
      const cy = clamp(a.y, b.y - b.h / 2, b.y + b.h / 2);
      const dx = a.x - cx, dy = a.y - cy;
      const d = Math.hypot(dx, dy);
      if (d >= RADIUS || d < 1e-6) continue;
      const share = give.get(b.id)!;
      const pen = RADIUS - d;
      const nx = dx / d, ny = dy / d;
      a.x += nx * pen * (1 - share); a.y += ny * pen * (1 - share);
      b.x -= nx * pen * share; b.y -= ny * pen * share;
      b.x = clamp(b.x, -half + b.w / 2 + 0.5, half - b.w / 2 - 0.5);
      b.y = clamp(b.y, -half + b.h / 2 + 0.5, half - b.h / 2 - 0.5);
    }
  }

  function step(): Frame {
    tick++;
    for (const a of agents) {
      if (--a.goalTicks <= 0) pickGoal(a);
      steer(a);
      a.x += Math.cos(a.heading) * a.speed * DT;
      a.y += Math.sin(a.heading) * a.speed * DT;
      a.energy = Math.max(0.05, a.energy - 0.008 * (1 + a.speed) * DT);
      if (a.goal === 'food') eat(a);

      if (a.signalTicks > 0 && --a.signalTicks === 0) a.signal = SIGNAL_OFF;
      else if (a.signalTicks === 0 && rng() < 0.004) flash(a, 1 + Math.floor(rng() * (SIGNAL_COUNT - 1)), 1 + rng() * 2);
    }
    separate();
    for (const a of agents) {
      shoveBlocks(a);
      a.x = clamp(a.x, -half + RADIUS, half - RADIUS);
      a.y = clamp(a.y, -half + RADIUS, half - RADIUS);
    }

    const due = regrow.filter((t) => t <= tick).length;
    regrow = regrow.filter((t) => t > tick);
    for (let i = 0; i < due; i++) food.push({ id: nextId++, kind: 'common', hidden: false, ...randomGroundPoint() });

    return {
      tick,
      creatures: agents.map(({ id, colony, x, y, heading, speed, size, energy, signal, carrying, holding, nectar, sprinting, load, young, stamina, dung }) =>
        ({ id, colony, x, y, heading, speed, size, energy, signal, carrying, holding, nectar, sprinting, load, young, stamina, dung })),
      food: food.map((f) => ({ ...f })),
      blocks: blocks.map((b) => ({ ...b })),
      stores: [],
      light: 1,
      eggs: [],
      flowers: [],
      flags: [],
    };
  }

  const info: WorldInfo = { width: MAP, height: MAP, tickHz: TICK_HZ, maxSpeed: MAX_SPEED, nests, midden: 0 };
  return { info, step };
}
