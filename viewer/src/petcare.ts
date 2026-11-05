export const HOUR = 3_600_000;
export const SAVE_KEY = 'terrarium.pet.v1';

// every number the care rules use, so balancing is one edit
export const RULES = {
  fullHours: 10,        // full to empty while awake; hungry (<= 20) after 8
  sadHours: 10,         // happiness 100 to 0 while awake
  hungry: 20,
  asleepRate: 0.1,      // asleep its metabolism slows: needs, neglect and illness all move at this fraction
  bed: 20 * 60,         // minutes after local midnight
  wake: 7.5 * 60,
  messNeglect: 1,       // droppings left that count as neglect
  illAfter: 8 * HOUR,   // of neglect, counted in awake time
  deadAfter: 12 * HOUR, // ill and untreated, awake time
  digest: HOUR / 2,
};

export interface Dropping { id: number; x: number; y: number }
export interface Care {
  version: 1;
  born: number;
  updated: number;
  offset: number;
  fullness: number;
  happiness: number;
  health: number;       // derived from neglect / sickFor, shown as a bar
  meals: number[];
  mess: Dropping[];
  serial: number;
  lastPlay: number;
  lastStroke: number;
  history: { at: number; text: string }[];
  bed: number;
  wake: number;
  neglect: number;      // awake-equivalent ms in a row with an unmet need
  sick: boolean;
  sickFor: number;      // ms ill
  dead: boolean;
  died: number;
}

export type Stage = 'well' | 'poorly' | 'ill' | 'very ill' | 'dead';

export function hatch(now: number): Care {
  return { version: 1, born: now, updated: now, offset: 0, fullness: 55,
    happiness: 65, health: 100, meals: [], mess: [], serial: 0,
    lastPlay: now - HOUR, lastStroke: now - HOUR,
    history: [{ at: now, text: 'Nim moved into the nursery.' }],
    bed: RULES.bed, wake: RULES.wake, neglect: 0, sick: false, sickFor: 0, dead: false, died: 0 };
}

function note(c: Care, text: string, at = c.updated) {
  c.history = [{ at, text }, ...c.history].slice(0, 12);
}

// next local time of day (minutes after midnight) strictly after t
export function nextAt(t: number, minutes: number): number {
  const d = new Date(t);
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, minutes).getTime();
  return x > t ? x : new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 0, minutes).getTime();
}

export function isAsleep(c: Care, t: number): boolean {
  const d = new Date(t);
  const m = d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60 + d.getMilliseconds() / 60000;
  return c.bed > c.wake ? m >= c.bed || m < c.wake : m >= c.bed && m < c.wake;
}

export function clock(minutes: number): string {
  const h = Math.floor(minutes / 60), m = Math.round(minutes % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

const neglected = (c: Care) => c.fullness <= 0 || c.happiness <= 0 || c.mess.length >= RULES.messNeglect;

export function stage(c: Care): Stage {
  if (c.dead) return 'dead';
  if (c.sick) return c.sickFor >= RULES.deadAfter / 2 - 1 ? 'very ill' : 'ill';
  return c.neglect >= RULES.illAfter / 2 - 1 ? 'poorly' : 'well';
}

function settle(c: Care) {
  if (!c.sick && !neglected(c)) c.neglect = 0;
  c.health = c.dead ? 0 : c.sick ? 40 * (1 - c.sickFor / RULES.deadAfter)
    : 100 - 60 * c.neglect / RULES.illAfter;
}

const warnings: Partial<Record<Stage, string>> = {
  poorly: 'Nim is feeling poorly.',
  ill: 'Nim is ill. Medicine will help.',
  'very ill': 'Nim is very ill and needs medicine now.',
};

// Integrate between events (meals, bedtime/wake, a need hitting a threshold, the
// illness and death clocks), so a long absence and frequent visits give the same
// result without stepping through every tick.
export function advance(c: Care, to: number): void {
  if (!Number.isFinite(to)) return;
  for (let guard = 0; c.updated < to && !c.dead && guard < 10_000; guard++) {
    const t = c.updated;
    const k = isAsleep(c, t) ? RULES.asleepRate : 1;
    const hungry = c.fullness <= RULES.hungry;
    const fall = k * 100 / (RULES.fullHours * HOUR);
    const sad = k * (100 / (RULES.sadHours * HOUR)) * (1 + (hungry ? 0.5 : 0) + Math.min(c.mess.length, 6) * 0.2);
    const unmet = neglected(c);
    const before = stage(c);
    const stops = [to, nextAt(t, c.bed), nextAt(t, c.wake)];
    if (c.meals.length) stops.push(Math.min(...c.meals));
    if (c.fullness > RULES.hungry) stops.push(t + (c.fullness - RULES.hungry) / fall);
    else if (c.fullness > 0) stops.push(t + c.fullness / fall);
    if (c.happiness > 0) stops.push(t + c.happiness / sad);
    if (c.sick) {
      stops.push(t + (RULES.deadAfter - c.sickFor) / k);
      if (c.sickFor < RULES.deadAfter / 2) stops.push(t + (RULES.deadAfter / 2 - c.sickFor) / k);
    } else if (unmet) {
      stops.push(t + (RULES.illAfter - c.neglect) / k);
      if (c.neglect < RULES.illAfter / 2) stops.push(t + (RULES.illAfter / 2 - c.neglect) / k);
    }
    let end = Math.min(...stops);
    if (!(end > t)) end = Math.min(to, t + 1);
    const dt = end - t;
    c.fullness = Math.max(0, c.fullness - dt * fall);
    c.happiness = Math.max(0, c.happiness - dt * sad);
    // snap tiny floating remainders at boundaries to avoid a zero-length loop
    if (c.fullness < 1e-8) c.fullness = 0;
    if (Math.abs(c.fullness - RULES.hungry) < 1e-8) c.fullness = RULES.hungry;
    if (c.happiness < 1e-8) c.happiness = 0;
    if (c.sick) c.sickFor += dt * k;
    else if (unmet) c.neglect += dt * k;
    c.updated = end;
    if (!c.sick && c.neglect >= RULES.illAfter - 1) { c.sick = true; c.sickFor = 0; c.neglect = RULES.illAfter; }
    if (c.sick && c.sickFor >= RULES.deadAfter - 1) {
      c.dead = true; c.died = end; c.sickFor = RULES.deadAfter;
      note(c, 'Nim has gone. Thank you for looking after it.', end);
    }
    const due = c.meals.filter(m => m <= end);
    c.meals = c.meals.filter(m => m > end);
    for (const _ of due) {
      const id = ++c.serial;
      const angle = id * 2.39996;
      const r = 0.8 + (id % 4) * 0.35;
      c.mess.push({ id, x: Math.cos(angle) * r, y: Math.sin(angle) * r });
      note(c, 'A little poop to clean up.', end);
    }
    settle(c);
    const after = stage(c);
    if (after !== before && warnings[after]) note(c, warnings[after]!, end);
  }
}

export type CareAction = 'feed' | 'clean' | 'play' | 'stroke' | 'medicine';
export function care(c: Care, action: CareAction): { ok: boolean; text: string } {
  if (c.dead) return { ok: false, text: 'Nim has gone. You can hatch a new egg.' };
  if (action !== 'clean' && action !== 'medicine' && isAsleep(c, c.updated)) {
    return { ok: false, text: `Shh, Nim is asleep until ${clock(c.wake)}. Medicine and tidying up are still fine.` };
  }
  let text: string;
  if (action === 'feed') {
    if (c.fullness > 85) return { ok: false, text: 'Nim is full. Save the next meal for later.' };
    c.fullness = Math.min(100, c.fullness + 30);
    c.happiness = Math.min(100, c.happiness + 4);
    c.meals.push(c.updated + RULES.digest);
    text = 'A meal for Nim. A poop will follow in about 30 minutes.';
  } else if (action === 'clean') {
    if (!c.mess.length) return { ok: false, text: 'All clean already.' };
    const count = c.mess.length;
    c.mess = [];
    c.happiness = Math.min(100, c.happiness + Math.min(12, count * 4));
    text = `Cleaned up ${count === 1 ? 'a poop' : `${count} poops`}. A fresh little garden.`;
  } else if (action === 'medicine') {
    if (!c.sick) return { ok: false, text: 'Nim isn’t ill. A meal, a game and a tidy garden keep it well.' };
    c.sick = false; c.sickFor = 0; c.neglect = 0;
    text = 'Medicine given. Nim is on the mend.';
  } else {
    const key = action === 'play' ? 'lastPlay' : 'lastStroke';
    const cooldown = action === 'play' ? 60_000 : 30_000;
    if (c.updated - c[key] < cooldown) return { ok: false, text: 'Nim is still enjoying that. Give it a moment.' };
    c[key] = c.updated;
    c.happiness = Math.min(100, c.happiness + (action === 'play' ? 18 : 6));
    text = action === 'play' ? 'A game of chase! Nim is happier.' : 'A little attention goes a long way.';
  }
  settle(c);
  note(c, text);
  return { ok: true, text };
}

export function mood(c: Care): string {
  const s = stage(c);
  if (s === 'dead') return 'Nim has gone';
  if (s === 'very ill') return 'Very ill. Needs medicine now';
  if (s === 'ill') return 'Ill. Needs medicine';
  if (s === 'poorly') return isAsleep(c, c.updated) ? 'Asleep, but poorly' : 'Feeling poorly';
  if (isAsleep(c, c.updated)) return 'Asleep';
  if (c.fullness <= RULES.hungry) return 'Hungry';
  if (c.mess.length >= 3) return 'Needs a cleanup';
  if (c.happiness < 25) return 'Wants some company';
  if (c.happiness > 75) return 'Happy little Nim';
  return 'Making itself at home';
}

export function readCare(raw: string): Care {
  const c = JSON.parse(raw) as Care;
  if (c && typeof c === 'object') {
    // saves from before the care rules had no sleep or illness fields
    c.bed ??= RULES.bed; c.wake ??= RULES.wake; c.neglect ??= 0;
    c.sick ??= false; c.sickFor ??= 0; c.dead ??= false; c.died ??= 0;
  }
  const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  const level = (v: unknown) => finite(v) && v >= 0 && v <= 100;
  if (!c || c.version !== 1 || ![c.born, c.updated, c.offset, c.lastPlay, c.lastStroke].every(finite)
    || c.updated < c.born || c.offset < 0 || ![c.fullness, c.happiness, c.health].every(level)
    || !Number.isSafeInteger(c.serial) || c.serial < 0 || !Array.isArray(c.meals)
    || c.meals.length > 100 || !c.meals.every(t => finite(t) && t >= c.updated) || !Array.isArray(c.mess)
    || c.mess.length > 1000 || !c.mess.every(d => d && Number.isSafeInteger(d.id) && finite(d.x) && finite(d.y))
    || !Array.isArray(c.history) || c.history.length > 12
    || !c.history.every(h => h && finite(h.at) && typeof h.text === 'string' && h.text.length < 500)
    || ![c.bed, c.wake].every(v => finite(v) && v >= 0 && v < 1440)
    || ![c.neglect, c.sickFor, c.died].every(v => finite(v) && v >= 0)
    || typeof c.sick !== 'boolean' || typeof c.dead !== 'boolean') {
    throw new Error('This nursery save could not be read. The original save has been kept.');
  }
  settle(c);
  return c;
}
