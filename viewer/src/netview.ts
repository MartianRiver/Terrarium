// The brain wired up (N, from the brain window): its senses and rays on the left, its own token's units as it
// enters and after each attention layer, and its actions on the right. Each unit is lit by its value now; the
// connections drawn are the strongest weights into each unit (sim/terrarium/mind.py wiring), glowing by what they
// carry this moment (the value coming in times the weight), and the rays reach each layer by how much attention
// they get. A wave runs left to right each time it chooses.

import { type MindTrack, type Thought } from './mindtrack';
import { ACTIONS, KINDS, SENSES, words } from './mindtext';

// [to, from, weight]
type Edge = [number, number, number];

export interface Wiring {
  senses: Edge[];
  layers: Edge[][];
  actions: Edge[];
  value: Edge[];
}

interface Node {
  x: number;
  y: number;
  // what the hover tip says, and the explanation key for a click
  tip: (t: Thought) => string;
  explain?: string;
}

const WARM = [240, 140, 40];
const COOL = [70, 130, 220];
// seconds for the wave to cross from senses to actions
const WAVE = 0.45;

function tint(v: number, alpha: number) {
  const [r, g, b] = v >= 0 ? WARM : COOL;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export class NetView {
  readonly root = document.createElement('div');
  private canvas = document.createElement('canvas');
  private tipEl = document.createElement('div');
  private foot = document.createElement('p');
  private track: MindTrack | null = null;
  private wiring: Wiring | null = null;
  private inputs: Node[] = [];
  private columns: Node[][] = [];
  private outputs: Node[] = [];
  private last: Thought | null = null;
  private since = 0;
  private hover: { x: number; y: number } | null = null;

  constructor(parent: HTMLElement) {
    this.root.className = 'net';
    this.root.hidden = true;
    this.root.setAttribute('aria-label', 'The brain wired up');
    const head = document.createElement('header');
    const title = document.createElement('h2');
    title.textContent = 'Wired up';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'mind-close';
    close.setAttribute('aria-label', 'Close the wired view');
    close.textContent = '×';
    close.addEventListener('click', () => this.toggle(false));
    head.append(title, close);
    this.tipEl.className = 'net-tip';
    this.tipEl.hidden = true;
    this.foot.className = 'net-foot';
    this.foot.textContent = 'Lit units are firing (warm positive, cool negative). Lines are the strongest connections into each unit, bright while they carry something. Hover a unit for its value; click a sense or an action for what it means.';
    this.root.append(head, this.canvas, this.tipEl, this.foot);
    this.canvas.addEventListener('mousemove', (e) => {
      const box = this.canvas.getBoundingClientRect();
      this.hover = { x: e.clientX - box.left, y: e.clientY - box.top };
    });
    this.canvas.addEventListener('mouseleave', () => (this.hover = null));
    this.canvas.addEventListener('click', () => {
      const node = this.nearest();
      if (!node?.explain) return;
      const [table, name] = node.explain.split(':');
      const w = words(table === 'sense' ? SENSES : table === 'kind' ? KINDS : ACTIONS, name);
      this.foot.textContent = `${w.label}: ${w.text}`;
    });
    parent.append(this.root);
  }

  get open() {
    return !this.root.hidden;
  }

  toggle(on = !this.open) {
    this.root.hidden = !on;
  }

  set(track: MindTrack | null, wiring: Wiring | null) {
    this.track = track;
    this.wiring = wiring;
    this.last = null;
  }

  draw(t: Thought | null, now: number) {
    if (!this.open) return;
    const ctx = this.fit();
    if (!ctx) return;
    const { width: w, height: h } = this.canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, w, h);
    if (!this.track || !t) {
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.font = '13px system-ui';
      ctx.fillText(this.track ? 'Not born yet, or no choice made yet.' : 'Open the brain window on a Terrikin first (B).', 16, 28);
      return;
    }
    if (t !== this.last) {
      this.last = t;
      this.since = now;
    }
    this.layout(w, h);
    const wave = (now - this.since) / 1000 / WAVE * 4;
    const boost = (gap: number) => 1 + 1.6 * Math.exp(-((wave - gap - 0.5) ** 2) / 0.12);
    const units = t.units;
    if (this.wiring) {
      const sense = this.inputs.slice(0, t.self.length);
      this.edges(ctx, this.wiring.senses, (f) => t.self[f], sense, this.columns[0], boost(0));
      this.wiring.layers.forEach((edges, l) => this.edges(ctx, edges, (f) => units[l][f], this.columns[l], this.columns[l + 1], boost(l + 1)));
      const last = this.columns.at(-1)!;
      this.edges(ctx, this.wiring.actions, (f) => t.summary[f], last, this.outputs, boost(units.length));
      this.edges(ctx, this.wiring.value, (f) => t.summary[f], last, [this.outputs.at(-1)!], boost(units.length));
    }
    this.attention(ctx, t, boost);
    this.nodes(ctx, t);
    this.labels(ctx, t, w);
    this.tip(t);
  }

  // size the canvas to its box at the screen's pixel ratio
  private fit() {
    const box = this.canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio, 2);
    const [pw, ph] = [Math.round(box.width * ratio), Math.round(box.height * ratio)];
    if (this.canvas.width !== pw || this.canvas.height !== ph) [this.canvas.width, this.canvas.height] = [pw, ph];
    const ctx = this.canvas.getContext('2d');
    ctx?.setTransform(ratio, 0, 0, ratio, 0, 0);
    return ctx;
  }

  private layout(w: number, h: number) {
    const head = this.track!.head;
    const { self, kinds, actions } = head.brain.schema;
    const top = 24, bottom = h - 12;
    const spread = (n: number, from: number, to: number) => Array.from({ length: n }, (_, i) => from + ((to - from) * (i + 0.5)) / n);
    const xs = [0.17, 0.4, 0.59, 0.78].map((f) => f * w);
    const split = top + (bottom - top) * (self.length / (self.length + head.rays.count + 2));
    this.inputs = [
      ...spread(self.length, top, split).map((y, i) => ({ x: xs[0], y, explain: `sense:${self[i]}`,
        tip: (t: Thought) => `${words(SENSES, self[i]).label}: ${t.self[i].toFixed(2)}` })),
      ...spread(head.rays.count, split + 16, bottom).map((y, i) => ({ x: xs[0], y,
        explain: undefined as string | undefined,
        tip: (t: Thought) => `ray ${i + 1} of ${head.rays.count} (from its right): ${KINDS[kinds[t.kinds[i]]]?.label ?? kinds[t.kinds[i]]}, ${(t.dist[i] * head.rays.range).toFixed(1)} m` })),
    ];
    const width = head.brain.shape.width;
    const names = ['as it enters', ...Array.from({ length: head.brain.shape.layers }, (_, l) => `after layer ${l + 1}`)];
    this.columns = names.map((name, c) => spread(width, top, bottom).map((y, u) => ({ x: xs[1 + c] ?? xs.at(-1)!, y,
      tip: (t: Thought) => `unit ${u + 1} ${name}: ${t.units[c][u].toFixed(2)}` })));
    const outs = [...actions, 'value'];
    this.outputs = spread(outs.length, top + (bottom - top) * 0.2, bottom - (bottom - top) * 0.2).map((y, i) => ({ x: 0.9 * w, y,
      explain: i < actions.length ? `action:${actions[i]}` : undefined,
      tip: (t: Thought) => i < actions.length ? `${words(ACTIONS, actions[i]).label}: ${t.odds[i] === null ? t.mean[i].toFixed(2) : `${Math.round(t.odds[i]! * 100)}% yes`}` : `how things look: ${t.value.toFixed(1)}` }));
  }

  private edges(ctx: CanvasRenderingContext2D, edges: Edge[], value: (from: number) => number, from: Node[], to: Node[], boost: number) {
    const carried = edges.map(([, f, wt]) => value(f) * wt);
    const most = Math.max(...carried.map(Math.abs), 1e-6);
    ctx.lineWidth = 0.6;
    edges.forEach(([t, f], i) => {
      const a = from[f], b = to[t];
      if (!a || !b) return;
      const share = Math.abs(carried[i]) / most;
      ctx.strokeStyle = share < 0.05 ? 'rgba(0,0,0,0.035)' : tint(carried[i], Math.min(1, share * 0.8 * boost));
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    });
  }

  // each ray reaches into each layer by how much its heads listen to it
  private attention(ctx: CanvasRenderingContext2D, t: Thought, boost: (gap: number) => number) {
    const rays = this.inputs.slice(t.self.length);
    const kinds = this.track!.head.brain.schema.kinds;
    t.attention.forEach((heads, l) => {
      const column = this.columns[l + 1];
      const mid = column[column.length >> 1];
      rays.forEach((r, i) => {
        const heard = heads.reduce((s, h) => s + h[i + 1], 0) / heads.length;
        if (heard < 0.01) return;
        ctx.strokeStyle = KINDS[kinds[t.kinds[i]]]?.colour ?? '#999';
        ctx.globalAlpha = Math.min(1, heard * 3 * boost(l + 1));
        ctx.lineWidth = 0.5 + heard * 10;
        ctx.beginPath();
        ctx.moveTo(r.x, r.y);
        ctx.bezierCurveTo((r.x + mid.x) / 2, r.y, (r.x + mid.x) / 2, mid.y, mid.x - 6, mid.y);
        ctx.stroke();
      });
    });
    ctx.globalAlpha = 1;
  }

  private nodes(ctx: CanvasRenderingContext2D, t: Thought) {
    const dot = (n: Node, r: number, fill: string) => {
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fill();
    };
    const kinds = this.track!.head.brain.schema.kinds;
    this.inputs.forEach((n, i) => {
      if (i < t.self.length) dot(n, 3.5, tint(t.self[i], 0.25 + 0.75 * Math.min(1, Math.abs(t.self[i]))));
      else {
        const r = i - t.self.length;
        dot(n, 2 + 3 * (1 - t.dist[r]), KINDS[kinds[t.kinds[r]]]?.colour ?? '#999');
      }
    });
    this.columns.forEach((column, c) => {
      const most = Math.max(...t.units[c].map(Math.abs), 1e-6);
      column.forEach((n, u) => dot(n, 2, tint(t.units[c][u], 0.12 + 0.88 * Math.abs(t.units[c][u]) / most)));
    });
    this.outputs.forEach((n, i) => {
      const strength = i < t.mean.length ? (t.odds[i] ?? Math.min(1, Math.abs(t.mean[i]))) : 0.6;
      dot(n, 5, tint(i < t.mean.length && t.odds[i] === null ? t.mean[i] : 1, 0.2 + 0.8 * strength));
    });
  }

  private labels(ctx: CanvasRenderingContext2D, t: Thought, w: number) {
    const { self, actions } = this.track!.head.brain.schema;
    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'right';
    self.forEach((s, i) => ctx.fillText(words(SENSES, s).label, this.inputs[i].x - 8, this.inputs[i].y + 3));
    ctx.fillText('rays, right → left', this.inputs[self.length].x - 8, this.inputs[self.length].y - 8);
    ctx.textAlign = 'left';
    [...actions, 'value'].forEach((a, i) => {
      const n = this.outputs[i];
      const label = i < actions.length ? words(ACTIONS, a).label : 'how things look';
      const extra = i < actions.length && t.odds[i] !== null && t.action[i] > 0 ? ' ✓' : '';
      ctx.fillText(label + extra, n.x + 9, n.y + 3);
    });
    ctx.textAlign = 'center';
    ctx.font = '11px system-ui';
    const heads = ['its senses', 'as it enters', ...t.attention.map((_, l) => `after layer ${l + 1}`)];
    [this.inputs[0], ...this.columns.map((c) => c[0])].forEach((n, i) => ctx.fillText(heads[i], n.x, 14));
    ctx.fillText('what it does', 0.9 * w, 14);
    ctx.textAlign = 'left';
  }

  private nearest(): Node | null {
    if (!this.hover) return null;
    let best: Node | null = null, d = 64;
    for (const n of [...this.inputs, ...this.columns.flat(), ...this.outputs]) {
      const dd = (n.x - this.hover.x) ** 2 + (n.y - this.hover.y) ** 2;
      if (dd < d) [best, d] = [n, dd];
    }
    return best;
  }

  private tip(t: Thought) {
    const node = this.nearest();
    this.tipEl.hidden = !node;
    if (!node || !this.hover) return;
    this.tipEl.textContent = node.tip(t);
    this.tipEl.style.left = `${this.hover.x + 14}px`;
    this.tipEl.style.top = `${this.hover.y + 40}px`;
  }
}
