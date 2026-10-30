// Who to watch in a nursery game and from where, so the camera shows the chase rather than whoever happens to be
// first: `lead` is the one Terrikin Follow stays on, and a shot is what Action frames. It reads the roles off the frames: tag's it lights its bulb (signal 0), seekers glow
// while they count (signal 2, then colony 1 seeks and colony 0 hides), and peekaboo's berry is marked hidden. A shot is a spot to look at, how far apart its subjects are (the camera pulls
// back to fit them) and the way to look from (behind the one acting, across to what it's after). It sticks with a
// pair for a while rather than flicking between near-equal ones. Anything that isn't a game: null, and Follow takes the first.
import type { CreatureState, Frame } from './world';

export interface Shot {
  x: number;
  y: number;
  spread: number; // metres between the subjects (0 for one)
  from: number | null; // ground angle (radians, sim space) the camera looks along, or null to keep its own
}

type Game = 'tag' | 'seek' | 'peek' | 'flag' | null;
type Spot = { x: number; y: number };

// a new pair takes over only when it's this much closer, and never sooner than HOLD seconds after the last change
const BETTER = 0.7;
const HOLD = 2.5;
// the subject's share of where the camera looks; the rest is what it's after
const LEAN = 0.6;
// closer than this (metres), the camera keeps the angle it has
const TURN_FROM = 2;

export class Director {
  // the one Terrikin most worth following right now (whoever's it, the seeker closing in, the one nearest the berry,
  // a hider during the count), or null outside a game
  lead: number | null = null;
  private game: Game = null;
  private subject: number | null = null;
  private partner: number | null = null;
  private since = Infinity;

  reset() {
    this.game = null;
    this.subject = this.partner = this.lead = null;
    this.since = Infinity;
  }

  // dt: seconds since the last shot
  shot(frame: Frame, dt: number): Shot | null {
    this.since += dt;
    this.game = this.game ?? kindOf(frame);
    const alive = frame.creatures.filter((c) => c.energy > 0);
    if (!this.game || !alive.length) {
      this.lead = null;
      return null;
    }
    if (this.game === 'peek') return this.peek(frame, alive);
    if (this.game === 'flag') return this.flag(frame, alive);
    if (this.game === 'seek' && alive.some((c) => c.signal === 2)) {
      // the count: watch where the hiders go, and follow one of them
      const hiders = alive.filter((c) => c.colony === 0);
      if (!hiders.some((c) => c.id === this.lead)) this.lead = hiders[0]?.id ?? null;
      return hiders.length ? { ...middle(hiders), spread: spreadOf(hiders), from: null } : null;
    }
    const [subjects, others] = this.sides(alive);
    if (!subjects.length || !others.length) {
      this.lead = subjects[0]?.id ?? null;
      return null;
    }
    this.choose(subjects, others);
    const s = alive.find((c) => c.id === this.subject)!;
    const p = alive.find((c) => c.id === this.partner)!;
    this.lead = s.id;
    return pair(s, p);
  }

  // who acts, and who they act on
  private sides(alive: CreatureState[]): [CreatureState[], CreatureState[]] {
    if (this.game === 'tag') {
      const it = alive.filter((c) => c.signal === 0);
      return [it, alive.filter((c) => c.signal !== 0)];
    }
    // seek after the count: seekers after hiders
    return [alive.filter((c) => c.colony === 1), alive.filter((c) => c.colony === 0)];
  }

  private choose(subjects: CreatureState[], others: CreatureState[]) {
    let best: [number, number, number] | null = null;
    for (const s of subjects) for (const o of others) {
      const d = dist(s, o);
      if (!best || d < best[2]) best = [s.id, o.id, d];
    }
    const s = subjects.find((c) => c.id === this.subject);
    const o = others.find((c) => c.id === this.partner);
    const kept = s && o ? dist(s, o) : Infinity;
    // a tag hands the subject on at once; otherwise a closer pair has to be clearly closer, and wait its turn
    const handed = this.game === 'tag' && !s;
    if (best && (handed || kept === Infinity || (best[2] < kept * BETTER && this.since > HOLD))) {
      if (best[0] !== this.subject || best[1] !== this.partner) this.since = 0;
      [this.subject, this.partner] = [best[0], best[1]];
    }
  }

  private peek(frame: Frame, alive: CreatureState[]): Shot | null {
    const berry = frame.food.find((f) => f.hidden) ?? frame.food[0];
    if (!berry) {
      this.lead = null;
      return { ...middle(alive), spread: spreadOf(alive), from: null };
    }
    const near = alive.reduce((a, b) => (dist(a, berry) <= dist(b, berry) ? a : b));
    this.lead = near.id;
    return pair(near, berry);
  }

  // capture the flag: a carrier and the nearest one who could take it off them; with no flag carried, whoever's
  // nearest the other side's flag, and that flag
  private flag(frame: Frame, alive: CreatureState[]): Shot | null {
    const carriers = alive.filter((c) => frame.flags.some((f) => f.carrier === c.id));
    if (carriers.length) {
      const held = carriers.find((c) => c.id === this.subject) ?? carriers[0];
      const others = alive.filter((c) => c.colony !== held.colony);
      if (!others.length) return null;
      const near = others.reduce((a, b) => (dist(a, held) <= dist(b, held) ? a : b));
      this.subject = this.lead = held.id;
      return pair(held, near);
    }
    let best: [CreatureState, Spot] | null = null;
    for (const c of alive) for (const f of frame.flags) {
      if (f.colony !== c.colony && (!best || dist(c, f) < dist(best[0], best[1]))) best = [c, f];
    }
    if (!best) return null;
    this.lead = best[0].id;
    return pair(best[0], best[1]);
  }
}

function kindOf(frame: Frame): Game {
  const cs = frame.creatures;
  if (frame.flags.length) return 'flag';
  if (cs.some((c) => c.signal === 2)) return 'seek';
  if (cs.some((c) => c.signal === 0) && new Set(cs.map((c) => c.colony)).size === 1) return 'tag';
  if (frame.food.some((f) => f.hidden)) return 'peek';
  return null;
}

function pair(s: Spot, p: Spot): Shot {
  const spread = dist(s, p);
  return {
    x: s.x * LEAN + p.x * (1 - LEAN),
    y: s.y * LEAN + p.y * (1 - LEAN),
    spread,
    // from behind the subject, looking across to what it's after; up close the way between them flips about, so not then
    from: spread > TURN_FROM ? Math.atan2(p.y - s.y, p.x - s.x) : null,
  };
}

function middle(cs: Spot[]): Spot {
  return { x: cs.reduce((t, c) => t + c.x, 0) / cs.length, y: cs.reduce((t, c) => t + c.y, 0) / cs.length };
}

function spreadOf(cs: Spot[]): number {
  const m = middle(cs);
  return 2 * Math.max(...cs.map((c) => dist(c, m)));
}

function dist(a: Spot, b: Spot) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}
