// The brain window (B): one Terrikin's brain as the replay plays, from its mind track (mindtrack.ts). What it sees
// as a fan of rays lit by attention, every head's attention, its senses, the summary it acts on, how things look to
// it over the episode, and what it does. Any part can be clicked for what it means (mindtext.ts).

import { clock } from './clock';
import { type MindTrack, type Thought } from './mindtrack';
import { ACTIONS, KINDS, PARTS, SENSES, type Words, words } from './mindtext';

const SVG = 'http://www.w3.org/2000/svg';
// the sight fan's drawing: centre and the length of a ray that saw nothing
const FAN = { w: 260, h: 170, cx: 130, cy: 112, r: 100 };

type Kids = (Node | string)[];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, ...kids: Kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...kids);
  return e;
}

function svg(tag: string, attrs: Record<string, string | number> = {}) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

// a bar from the middle: left for negative, right for positive
function centred(fill: HTMLElement, v: number) {
  const x = Math.max(-1, Math.min(1, v));
  fill.style.left = `${50 + Math.min(0, x) * 50}%`;
  fill.style.width = `${Math.abs(x) * 50}%`;
}

// cool for negative, warm for positive
function diverging(v: number) {
  const x = Math.max(-1, Math.min(1, v / 2.5));
  return x < 0 ? `rgba(70, 130, 220, ${-x})` : `rgba(240, 140, 40, ${x})`;
}

export interface Note {
  text: string;
  // a button under the note, e.g. to record the replay again here
  action?: { label: string; run: () => void };
}

export class MindPanel {
  readonly root = el('aside', { class: 'mind', 'aria-label': 'Brain window' });
  private title = el('h2');
  private note = el('p', { class: 'mind-note', role: 'status' });
  private body = el('div', { class: 'mind-body' });
  private info = el('div', { class: 'mind-info' });
  private track: MindTrack | null = null;
  private shown: Thought | null = null;
  // per part, what update() fills in
  private rays: SVGLineElement[] = [];
  private ends: SVGCircleElement[] = [];
  private rings: SVGCircleElement[] = [];
  private cells: HTMLElement[][][] = [];
  private senses: { fill: HTMLElement; num: HTMLElement }[] = [];
  private summary = document.createElement('canvas');
  private valueMark = svg('circle', { r: 3.5, class: 'mind-mark' }) as SVGCircleElement;
  private valueNum = el('span', { class: 'mind-num' });
  private span = { lo: 0, hi: 1, first: 0, last: 1 };
  private actions: { fill: HTMLElement; num: HTMLElement; yes: HTMLElement | null }[] = [];
  // opens the wired-up view (netview.ts)
  wired = () => {};

  constructor(parent: HTMLElement) {
    const close = el('button', { type: 'button', class: 'mind-close', 'aria-label': 'Close the brain window' }, '×');
    close.addEventListener('click', () => this.toggle(false));
    const wired = el('button', { type: 'button', class: 'mind-wired', title: 'See it wired up (N)' }, 'Wired');
    wired.addEventListener('click', () => this.wired());
    this.root.append(el('header', {}, this.title, wired, close), this.note, this.body, this.info);
    this.root.hidden = true;
    this.root.addEventListener('click', (e) => {
      const target = (e.target as Element).closest('[data-explain]');
      if (target) this.explain(target.getAttribute('data-explain')!);
    });
    this.explain('');
    parent.append(this.root);
  }

  get open() {
    return !this.root.hidden;
  }

  toggle(on = !this.open) {
    this.root.hidden = !on;
  }

  // nothing to show yet, or why not
  say(title: string, note: Note | null) {
    this.title.textContent = title;
    this.note.replaceChildren(note?.text ?? '');
    this.note.hidden = !note;
    if (note?.action) {
      const b = el('button', { type: 'button' }, note.action.label);
      b.addEventListener('click', note.action.run);
      this.note.append(' ', b);
    }
  }

  show(track: MindTrack | null) {
    this.track = track;
    this.shown = null;
    this.body.replaceChildren();
    if (!track) return;
    const { head } = track;
    const values = track.thoughts.map((t) => t.value);
    this.span = { lo: Math.min(...values), hi: Math.max(...values), first: track.thoughts[0]?.tick ?? 0, last: track.thoughts.at(-1)?.tick ?? 1 };
    this.body.append(
      this.section('sight', this.buildSight(track)),
      this.section('attention', this.buildAttention(track)),
      this.section('senses', this.buildSenses(head.brain.schema.self)),
      this.section('summary', this.buildSummary(head.brain.shape.width)),
      this.section('value', this.buildValue(track)),
      this.section('actions', this.buildActions(head.brain.schema.actions)),
    );
  }

  // draw what it was thinking at this tick
  update(tick: number) {
    const t = this.track?.at(tick) ?? null;
    if (!this.open || t === this.shown) return;
    this.shown = t;
    if (!t || !this.track) return;
    const last = t.attention.at(-1)!;
    // how much each ray is listened to in the last layer, over its heads, scaled so the most is 1
    const heard = t.kinds.map((_, i) => last.reduce((s, head) => s + head[i + 1], 0) / last.length);
    const most = Math.max(...heard, 1e-6);
    t.kinds.forEach((k, i) => {
      const kind = this.track!.head.brain.schema.kinds[k];
      const end = this.fanPoint(i, t.dist[i]);
      const line = this.rays[i];
      line.setAttribute('x2', String(end.x));
      line.setAttribute('y2', String(end.y));
      line.setAttribute('stroke', KINDS[kind]?.colour ?? '#999');
      line.setAttribute('stroke-width', String(1 + 4 * heard[i] / most));
      line.setAttribute('stroke-opacity', String(0.25 + 0.75 * heard[i] / most));
      line.dataset.explain = `kind:${kind}`;
      for (const dot of [this.ends[i], this.rings[i]]) {
        dot.setAttribute('cx', String(end.x));
        dot.setAttribute('cy', String(end.y));
      }
      this.ends[i].setAttribute('fill', KINDS[kind]?.colour ?? '#999');
      this.ends[i].style.display = kind === 'nothing' ? 'none' : '';
      this.rings[i].style.display = t.nestmate[i] ? '' : 'none';
    });
    t.attention.forEach((layer, l) => layer.forEach((head, h) => {
      // me first, then the rays from its left to its right, as the fan draws them
      [head[0], ...head.slice(1).reverse()].forEach((w, c) => {
        this.cells[l][h][c].style.background = `rgba(255, 200, 60, ${Math.min(1, w * 1.5)})`;
      });
    }));
    t.self.forEach((v, i) => {
      centred(this.senses[i].fill, v);
      this.senses[i].num.textContent = v.toFixed(2);
    });
    const ctx = this.summary.getContext('2d');
    if (ctx) t.summary.forEach((v, i) => {
      ctx.fillStyle = '#fff';
      ctx.fillRect(i, 0, 1, 1);
      ctx.fillStyle = diverging(v);
      ctx.fillRect(i, 0, 1, 1);
    });
    const p = this.valuePoint(t.tick, t.value);
    this.valueMark.setAttribute('cx', String(p.x));
    this.valueMark.setAttribute('cy', String(p.y));
    this.valueNum.textContent = `${t.value.toFixed(1)} at ${clock(t.tick / this.track.head.tickHz)}`;
    t.mean.forEach((m, i) => {
      const row = this.actions[i];
      const odds = t.odds[i];
      if (odds === null) {
        centred(row.fill, m);
        row.num.textContent = Math.max(-1, Math.min(1, m)).toFixed(2);
      } else {
        row.fill.style.left = '0';
        row.fill.style.width = `${odds * 100}%`;
        row.num.textContent = `${Math.round(odds * 100)}%`;
        row.yes!.textContent = t.action[i] > 0 ? '✓ yes' : '';
      }
    });
  }

  private explain(key: string) {
    const [table, name] = key.split(':');
    const tables: Record<string, Record<string, Words>> = { part: PARTS, sense: SENSES, kind: KINDS, action: ACTIONS };
    const w = key ? words(tables[table] ?? PARTS, name) : { label: 'Click any part', text: 'Click a part of the brain, a sense, a ray or an action to see what it means.' };
    this.info.replaceChildren(el('h4', {}, w.label), el('p', {}, w.text));
  }

  private section(part: string, ...kids: Kids) {
    const w = PARTS[part];
    return el('section', {}, el('h3', { 'data-explain': `part:${part}`, tabindex: '0' }, w.label, el('span', { class: 'mind-what' }, ' ?')), ...kids);
  }

  private fanPoint(i: number, dist: number) {
    const { count, fov } = this.track!.head.rays;
    // ray 0 is on its right; up the page is straight ahead
    const a = count > 1 ? -fov / 2 + (fov * i) / (count - 1) : 0;
    return { x: FAN.cx - Math.sin(a) * dist * FAN.r, y: FAN.cy - Math.cos(a) * dist * FAN.r };
  }

  private buildSight(track: MindTrack) {
    const fan = svg('svg', { viewBox: `0 0 ${FAN.w} ${FAN.h}`, class: 'mind-fan', role: 'img', 'aria-label': 'Its rays' });
    fan.append(svg('circle', { cx: FAN.cx, cy: FAN.cy, r: FAN.r, class: 'mind-range' }));
    this.rays = [];
    this.ends = [];
    this.rings = [];
    for (let i = 0; i < track.head.rays.count; i++) {
      const line = svg('line', { x1: FAN.cx, y1: FAN.cy, x2: FAN.cx, y2: FAN.cy, 'stroke-linecap': 'round' }) as SVGLineElement;
      const end = svg('circle', { r: 4 }) as SVGCircleElement;
      const ring = svg('circle', { r: 7, class: 'mind-mate' }) as SVGCircleElement;
      this.rays.push(line);
      this.ends.push(end);
      this.rings.push(ring);
      fan.append(line, ring, end);
    }
    fan.append(svg('circle', { cx: FAN.cx, cy: FAN.cy, r: 7, class: 'mind-me' }));
    const legend = el('div', { class: 'mind-legend' }, ...track.head.brain.schema.kinds.filter((k) => k !== 'nothing').map((k) =>
      el('span', { 'data-explain': `kind:${k}` }, el('i', { style: `background:${KINDS[k]?.colour ?? '#999'}` }), KINDS[k]?.label ?? k)));
    return el('div', { 'data-explain': 'part:sight' }, fan, legend);
  }

  private buildAttention(track: MindTrack) {
    const { layers, heads } = track.head.brain.shape;
    const grid = el('div', { class: 'mind-attention', 'data-explain': 'part:attention' });
    this.cells = [];
    for (let l = 0; l < layers; l++) {
      const rows: HTMLElement[][] = [];
      grid.append(el('div', { class: 'mind-layer' }, `layer ${l + 1}`, el('span', { class: 'mind-small' }, ' · me | its left … its right')));
      for (let h = 0; h < heads; h++) {
        const cells = Array.from({ length: track.head.rays.count + 1 }, (_, c) => el('i', c === 0 ? { class: 'me' } : {}));
        rows.push(cells);
        grid.append(el('div', { class: 'mind-head' }, ...cells));
      }
      this.cells.push(rows);
    }
    return grid;
  }

  private buildSenses(names: string[]) {
    this.senses = [];
    return el('div', { class: 'mind-rows' }, ...names.map((name) => {
      const fill = el('i');
      const num = el('span', { class: 'mind-num' });
      this.senses.push({ fill, num });
      return el('div', { class: 'mind-row', 'data-explain': `sense:${name}` }, el('span', {}, words(SENSES, name).label), el('b', { class: 'mind-bar centred' }, fill), num);
    }));
  }

  private buildSummary(width: number) {
    this.summary.width = width;
    this.summary.height = 1;
    this.summary.className = 'mind-summary';
    this.summary.dataset.explain = 'part:summary';
    return this.summary;
  }

  private valuePoint(tick: number, value: number) {
    const { lo, hi, first, last } = this.span;
    return { x: 4 + ((tick - first) / Math.max(1, last - first)) * 252, y: 46 - ((value - lo) / Math.max(1e-6, hi - lo)) * 42 };
  }

  private buildValue(track: MindTrack) {
    const chart = svg('svg', { viewBox: '0 0 260 50', class: 'mind-value', 'data-explain': 'part:value' });
    const points = track.thoughts.map((t) => { const p = this.valuePoint(t.tick, t.value); return `${p.x.toFixed(1)},${p.y.toFixed(1)}`; });
    chart.append(svg('polyline', { points: points.join(' '), class: 'mind-line' }), this.valueMark);
    return el('div', {}, chart, this.valueNum);
  }

  private buildActions(names: string[]) {
    this.actions = [];
    return el('div', { class: 'mind-rows' }, ...names.map((name) => {
      const fill = el('i');
      const num = el('span', { class: 'mind-num' });
      const steering = name === 'thrust' || name === 'turn';
      const yes = steering ? null : el('span', { class: 'mind-yes' });
      this.actions.push({ fill, num, yes });
      return el('div', { class: 'mind-row', 'data-explain': `action:${name}` }, el('span', {}, words(ACTIONS, name).label),
        el('b', { class: `mind-bar${steering ? ' centred' : ''}` }, fill), num, ...(yes ? [yes] : []));
    }));
  }
}
