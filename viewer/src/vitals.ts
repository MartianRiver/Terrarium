import './vitals.css';
import type { CreatureState, Frame, WorldInfo } from './world';

// the followed Terrikin's card (top left): only the rows its world uses, worked out from the frames, since a replay's
// config is never relied on. A row turns on the first time the episode shows it (energy below full, stamina below
// full, something carried, a jump) and stays on until the next episode.
type Row = 'home' | 'fed' | 'go' | 'holds' | 'jump';
const ROWS: Row[] = ['home', 'fed', 'go', 'holds', 'jump'];
const WORDS: Record<Row, string> = { home: 'home', fed: 'fed', go: 'go', holds: 'carrying', jump: 'jump' };

export interface Facing { x: number; z: number } // the camera's forward along the ground, in the scene's x/z

export class Vitals {
  private box = document.createElement('section');
  private title = document.createElement('h2');
  private rows = new Map<Row, { li: HTMLLIElement; value: HTMLElement; bar?: HTMLElement }>();
  private arrow = document.createElement('span');
  private seen = new Set<Row>();

  constructor(parent: HTMLElement, private info: WorldInfo) {
    this.box.className = 'vitals';
    this.box.hidden = true;
    this.box.setAttribute('aria-label', 'The Terrikin you follow');
    const list = document.createElement('ul');
    for (const row of ROWS) {
      const li = document.createElement('li');
      li.hidden = true;
      li.dataset.row = row;
      const name = document.createElement('span');
      name.className = 'vitals-name';
      name.textContent = WORDS[row];
      const value = document.createElement('span');
      value.className = 'vitals-value';
      li.append(name);
      let bar: HTMLElement | undefined;
      if (row === 'fed' || row === 'go') {
        const track = document.createElement('span');
        track.className = 'vitals-bar';
        bar = document.createElement('i');
        track.append(bar);
        li.append(track);
      }
      if (row === 'home') {
        this.arrow.className = 'vitals-arrow';
        this.arrow.textContent = '↑';
        li.append(this.arrow);
      }
      li.append(value);
      list.append(li);
      this.rows.set(row, { li, value, bar });
    }
    this.box.append(this.title, list);
    parent.append(this.box);
    // keep clear of the bar along the top, however many lines it wraps to
    const hud = document.getElementById('hud');
    if (hud) new ResizeObserver(() => { this.box.style.top = `${hud.getBoundingClientRect().bottom + 10}px`; }).observe(hud);
  }

  reset(info: WorldInfo) {
    this.info = info;
    this.seen.clear();
    for (const { li } of this.rows.values()) li.hidden = true;
  }

  // c: the followed Terrikin as drawn this frame (null hides the card); frame for the flags
  show(c: CreatureState | null, name: string, frame: Frame | null, facing: Facing) {
    this.box.hidden = !c;
    if (!c) return;
    if (this.title.textContent !== name) this.title.textContent = name;
    const nest = this.info.nests.find((n) => n.colony === c.colony);
    if (nest) this.seen.add('home');
    if (c.energy < 0.999) this.seen.add('fed');
    if (c.stamina < 0.999) this.seen.add('go');
    const holds = holding(c, frame, this.info.tree !== null);
    if (holds) this.seen.add('holds');
    if (c.z > 0.01) this.seen.add('jump');
    for (const row of this.seen) this.rows.get(row)!.li.hidden = false;

    if (nest) {
      const dx = nest.x - c.x;
      const dz = nest.y - c.y;
      const far = Math.hypot(dx, dz) - nest.radius;
      const inside = far <= 0;
      this.arrow.style.visibility = inside ? 'hidden' : '';
      this.arrow.style.transform = `rotate(${turnTo(dx, dz, facing)}rad)`;
      this.set('home', inside ? 'in the nest' : `${far.toFixed(far < 10 ? 1 : 0)} m`);
    }
    this.set('fed', c.energy < 0.25 ? 'starving' : c.energy < 0.4 ? 'hungry' : c.energy > 0.9 ? 'full' : '', c.energy);
    this.set('go', c.stamina < 0.25 ? 'worn out' : c.stamina < 0.5 ? 'tired' : '', c.stamina);
    this.set('holds', holds || 'nothing');
    this.set('jump', c.z > 0.01 ? `${c.z.toFixed(1)} m up` : 'on the ground');
  }

  private set(row: Row, text: string, share?: number) {
    const r = this.rows.get(row)!;
    if (r.value.textContent !== text) r.value.textContent = text;
    if (r.bar && share !== undefined) {
      r.bar.style.width = `${Math.round(Math.max(0, Math.min(1, share)) * 100)}%`;
      r.li.dataset.low = String(share < 0.4);
    }
  }
}

// how far clockwise of screen up something (dx, dz) away lies: screen up is the camera's forward along the ground,
// screen right (-forward.z, forward.x)
export function turnTo(dx: number, dz: number, facing: Facing) {
  return Math.atan2(dx * -facing.z + dz * facing.x, dx * facing.x + dz * facing.z);
}

export function holding(c: CreatureState, frame: Frame | null, tree: boolean) {
  if (frame?.flags.some((f) => f.carrier === c.id)) return 'a flag';
  if (c.dung) return 'a dropping';
  if (c.load) return 'a berry';
  if (c.carrying) return tree ? 'an apple, for home' : 'food in its crop';
  if (c.holding) return 'a block';
  return '';
}
