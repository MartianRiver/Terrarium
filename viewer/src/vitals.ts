import './vitals.css';
import type { CreatureState, Frame, WorldInfo } from './world';

// the followed nim's card (top left): only the rows its world uses, worked out from the frames, since a replay's
// config is never relied on for what the frames show. A row turns on the first time the episode shows it (energy
// below full, stamina below full, water in the frames, something carried, a jump, jelly in the store) and stays on until the next
// episode. The compass and notes rows come from the replay's header instead (see hasCompass, notesLabel).
type Row = 'home' | 'compass' | 'fed' | 'water' | 'go' | 'holds' | 'jump' | 'store' | 'notes';
const ROWS: Row[] = ['home', 'compass', 'fed', 'water', 'go', 'holds', 'jump', 'store', 'notes'];
const WORDS: Record<Row, string> = { home: 'home', compass: 'facing', fed: 'fed', water: 'water', go: 'go', holds: 'carrying', jump: 'jump', store: 'store', notes: 'notes' };
const POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

export interface Facing { x: number; z: number } // the camera's forward along the ground, in the scene's x/z

// what the card says right now, as plain data: the DOM paints it, and the reel harness draws it on its own canvas
// (a clip is cut from the WebGL canvas, which the DOM never reaches)
export interface VitalsLine {
  row: Row;
  name: string;
  text: string;
  share?: number; // a bar, 0..1
  low?: boolean;
  arrow?: number; // radians clockwise of screen up
  dial?: { north: number; needle: number }; // north's angle on screen; the needle's from north
}
export interface VitalsModel { title: string; lines: VitalsLine[] }

// ?vitals=1 / on / big forces the card on for the focused nim under any camera (big: for clips); 0 / off forces it off
export function vitalsAsk(search: string): { force: boolean | null; big: boolean } {
  const v = new URLSearchParams(search).get('vitals');
  if (v === null) return { force: null, big: false };
  const word = v.toLowerCase();
  if (word === '0' || word === 'off' || word === 'false') return { force: false, big: false };
  return { force: true, big: word === 'big' };
}

// the replay header's `source`: only what the card reads from it
export type Meta = Record<string, unknown>;

// a replay can't say whether its brain has the compass (it's in every brain from schema v19, and the header holds no
// schema), so it's shown wherever the way home isn't simply felt from anywhere: a world with a tree, or [home] far
export function hasCompass(info: WorldInfo, meta: Meta = {}) {
  const far = ((meta.config as { home?: { far?: number } } | undefined)?.home?.far) ?? 0;
  return info.tree !== null || far > 0;
}

// whether the brain's notes (what it remembers between trips) are kept or wiped: the header's brain.notes as written,
// else a brain id ending -wiped; nothing when neither says
export function notesLabel(meta: Meta = {}) {
  const brain = meta.brain as { id?: unknown; notes?: unknown } | string | undefined;
  if (brain && typeof brain === 'object' && typeof brain.notes === 'string' && brain.notes) return brain.notes;
  const id = typeof brain === 'string' ? brain : typeof brain?.id === 'string' ? brain.id : '';
  return id.endsWith('-wiped') ? 'wiped each time it gets home' : '';
}

// how far clockwise of screen up something (dx, dz) away lies: screen up is the camera's forward along the ground,
// screen right (-forward.z, forward.x)
export function turnTo(dx: number, dz: number, facing: Facing) {
  return Math.atan2(dx * -facing.z + dz * facing.x, dx * facing.x + dz * facing.z);
}

// north is up the screen in the default overview (scene -z, sim -y); a heading is 0 = +x, counter-clockwise
export const NORTH: Facing = { x: 0, z: -1 };
export const bearing = (heading: number) => turnTo(Math.cos(heading), Math.sin(heading), NORTH);
export function pointName(bear: number) {
  return POINTS[(Math.round(bear / (Math.PI / 4)) % 8 + 8) % 8];
}

// how thirsty a nim with this much water left says it is: nothing in between
export const thirst = (left: number) => (left < 0.25 ? 'parched' : left < 0.4 ? 'thirsty' : left > 0.9 ? 'full' : '');

export function holding(c: CreatureState, frame: Frame | null, tree: boolean) {
  if (frame?.flags.some((f) => f.carrier === c.id)) return 'a flag';
  if (c.dung) return 'a dropping';
  if (c.load) return 'a berry';
  if (c.carrying) return tree ? 'an apple, for home' : 'food in its crop';
  if (c.holding) return 'a block';
  return '';
}

export class Vitals {
  model: VitalsModel | null = null;
  private box = document.createElement('section');
  private title = document.createElement('h2');
  private rows = new Map<Row, { li: HTMLLIElement; value: HTMLElement; bar?: HTMLElement; arrow?: HTMLElement }>();
  private dial = { box: document.createElement('span'), north: document.createElement('span'), needle: document.createElement('span') };
  private seen = new Set<Row>();
  private compass = false;
  private notes = '';

  constructor(parent: HTMLElement, private info: WorldInfo, meta: Meta = {}, big = false) {
    this.box.className = big ? 'vitals big' : 'vitals';
    this.box.hidden = true;
    this.box.setAttribute('aria-label', 'The nim you follow');
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
      let arrow: HTMLElement | undefined;
      if (row === 'fed' || row === 'water' || row === 'go') {
        const track = document.createElement('span');
        track.className = 'vitals-bar';
        bar = document.createElement('i');
        track.append(bar);
        li.append(track);
      }
      if (row === 'home') {
        arrow = document.createElement('span');
        arrow.className = 'vitals-arrow';
        arrow.textContent = '↑';
        li.append(arrow);
      }
      if (row === 'compass') {
        const { box, north, needle } = this.dial;
        box.className = 'vitals-dial';
        north.className = 'vitals-north';
        north.textContent = 'N';
        needle.className = 'vitals-needle';
        box.append(north, needle);
        box.setAttribute('role', 'img');
        li.append(box);
      }
      li.append(value);
      list.append(li);
      this.rows.set(row, { li, value, bar, arrow });
    }
    this.box.append(this.title, list);
    parent.append(this.box);
    this.reset(info, meta);
    // keep clear of the bar along the top, however many lines it wraps to
    const hud = document.getElementById('hud');
    if (hud) new ResizeObserver(() => { this.box.style.top = `${hud.getBoundingClientRect().bottom + 10}px`; }).observe(hud);
  }

  reset(info: WorldInfo, meta: Meta = {}) {
    this.info = info;
    this.compass = hasCompass(info, meta);
    this.notes = notesLabel(meta);
    this.seen.clear();
    for (const { li } of this.rows.values()) li.hidden = true;
  }

  // c: the followed nim as drawn this frame (null hides the card); frame for the flags and the store
  show(c: CreatureState | null, name: string, frame: Frame | null, facing: Facing) {
    this.box.hidden = !c;
    if (!c) {
      this.model = null;
      return;
    }
    if (this.title.textContent !== name) this.title.textContent = name;
    const nest = this.info.nests.find((n) => n.colony === c.colony);
    const jelly = frame?.stores.find((s) => s.colony === c.colony)?.jelly ?? 0;
    const holds = holding(c, frame, this.info.tree !== null);
    if (nest) this.seen.add('home');
    if (this.compass) this.seen.add('compass');
    if (c.energy < 0.999) this.seen.add('fed');
    // there from the first frame wherever the world has ponds: a nim's thirst is the point of them
    if (c.water !== undefined) this.seen.add('water');
    if (c.stamina < 0.999) this.seen.add('go');
    if (holds) this.seen.add('holds');
    if (c.z > 0.01) this.seen.add('jump');
    if (jelly > 0) this.seen.add('store');
    if (this.notes) this.seen.add('notes');

    const lines: VitalsLine[] = [];
    for (const row of ROWS) {
      if (!this.seen.has(row)) continue;
      const line: VitalsLine = { row, name: WORDS[row], text: '' };
      if (row === 'home' && nest) {
        const dx = nest.x - c.x;
        const dz = nest.y - c.y;
        const far = Math.hypot(dx, dz) - nest.radius;
        line.text = far <= 0 ? 'in the nest' : `${far.toFixed(far < 10 ? 1 : 0)} m`;
        if (far > 0) line.arrow = turnTo(dx, dz, facing);
      } else if (row === 'compass') {
        const bear = bearing(c.heading);
        line.text = pointName(bear);
        line.dial = { north: turnTo(NORTH.x, NORTH.z, facing), needle: bear };
      } else if (row === 'fed') {
        line.text = c.energy < 0.25 ? 'starving' : c.energy < 0.4 ? 'hungry' : c.energy > 0.9 ? 'full' : '';
        line.share = c.energy;
      } else if (row === 'water') {
        const left = c.water ?? 1;
        line.text = thirst(left);
        line.share = left;
      } else if (row === 'go') {
        line.text = c.stamina < 0.25 ? 'worn out' : c.stamina < 0.5 ? 'tired' : '';
        line.share = c.stamina;
      } else if (row === 'holds') {
        line.text = holds || 'nothing';
      } else if (row === 'jump') {
        line.text = c.z > 0.01 ? `${c.z.toFixed(1)} m up` : 'on the ground';
      } else if (row === 'store') {
        line.text = `${Number.isInteger(jelly) ? jelly : jelly.toFixed(1)} jelly`;
      } else if (row === 'notes') {
        line.text = this.notes;
      } else continue;
      if (line.share !== undefined) line.low = line.share < 0.4;
      lines.push(line);
    }
    this.model = { title: name, lines };
    this.paint(lines);
  }

  private paint(lines: VitalsLine[]) {
    for (const [row, r] of this.rows) r.li.hidden = !lines.some((l) => l.row === row);
    for (const l of lines) {
      const r = this.rows.get(l.row)!;
      if (r.value.textContent !== l.text) r.value.textContent = l.text;
      if (r.bar && l.share !== undefined) {
        r.bar.style.width = `${Math.round(Math.max(0, Math.min(1, l.share)) * 100)}%`;
        r.li.dataset.low = String(l.low);
      }
      if (r.arrow) {
        r.arrow.style.visibility = l.arrow === undefined ? 'hidden' : '';
        if (l.arrow !== undefined) r.arrow.style.transform = `rotate(${l.arrow}rad)`;
      }
      if (l.dial) {
        this.dial.north.style.transform = `rotate(${l.dial.north}rad)`;
        this.dial.needle.style.transform = `rotate(${l.dial.north + l.dial.needle}rad)`;
        this.dial.box.setAttribute('aria-label', `facing ${l.text}`);
      }
    }
  }
}
