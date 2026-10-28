// Play as one Terrikin (local only, ?play[=run id]): a game on the runs server (sim play.py) in a run's world, the
// rest steered by its newest brain. Frames come a few ticks at a time, each request carrying what you're doing, so
// the game runs at the viewer's pace and stops when it pauses. A panel shows the controls this world has and how
// you're doing next to the brain's Terrikins.
import * as THREE from 'three';
import { clock } from './clock';
import { parseReplay } from './replay';
import type { Frame, WorldInfo } from './world';

interface Score {
  you: { alive: boolean; seconds: number; meals: number; energy: number; per_minute: number };
  brain: { seconds: number; per_minute: number };
  colonies: number[];
  seconds: number;
  length: number;
  over: boolean;
}

interface Start {
  game: string;
  label: string;
  header: unknown;
  frame: unknown;
  you: number;
  controls: string[];
  score: Score;
}

// yes/no actions by key, held down for as long as you want a yes
const ACTIONS: Record<string, { keys: string[]; label: string; what: string }> = {
  sprint: { keys: ['shift'], label: 'Shift', what: 'sprint' },
  eat: { keys: ['e'], label: 'E', what: 'eat' },
  unload: { keys: ['q'], label: 'Q', what: 'unload at your nest' },
  grab: { keys: ['g'], label: 'G', what: 'grab a block' },
  carry: { keys: [' '], label: 'Space', what: 'pick up or put down a berry' },
};
const AHEAD = 4;
const BATCH = 2;
const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const wrap = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));

const parse = (header: unknown, raw: unknown[]) => parseReplay([header, ...raw].map((x) => JSON.stringify(x)).join('\n'));
const frames = (header: unknown, raw: unknown[]): Frame[] => (raw.length ? parse(header, raw).frames : []);

async function post(url: string, body: object) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const got = await res.json().catch(() => null);
  if (!res.ok) throw new Error(got?.error ?? `the server said ${res.status}`);
  return got;
}

export class Game {
  readonly info: WorldInfo;
  readonly you: number;
  readonly token: string;
  private buffer: Frame[];
  private last: Frame;
  private asking = false;
  private score: Score;
  private failed = '';
  private held = new Set<string>();
  private pointer: { x: number; y: number } | null = null;
  private caster = new THREE.Raycaster();
  private panel: HTMLElement;
  private stop: () => void;

  private constructor(private start: Start, private camera: THREE.Camera, private canvas: HTMLCanvasElement) {
    const { info, frames: first } = parse(start.header, [start.frame]);
    this.info = info;
    this.you = start.you;
    this.token = start.game;
    this.buffer = [...first];
    this.last = first[0];
    this.score = start.score;
    this.panel = document.createElement('div');
    this.panel.id = 'play';
    document.body.append(this.panel);
    this.stop = this.listen();
    this.show();
  }

  static async begin(run: string | null, camera: THREE.Camera, canvas: HTMLCanvasElement): Promise<Game> {
    return new Game(await post('/api/play', run ? { run } : {}), camera, canvas);
  }

  // the viewer's Source

  step(): Frame | null {
    const next = this.buffer.shift();
    if (next) this.last = next;
    void this.ask();
    return next ?? this.last;
  }

  ready(): boolean {
    void this.ask();
    return this.buffer.length > 0;
  }

  label(): string {
    return `${this.start.label.replace(/^\d{8}-\d{6}-/, '')} · ${clock(this.score.seconds)} / ${clock(this.score.length)}`;
  }

  end() {
    this.stop();
    this.panel.remove();
  }

  private async ask() {
    if (this.asking || this.score.over || this.failed || this.buffer.length >= AHEAD) return;
    this.asking = true;
    try {
      const got = await post(`/api/play/${this.token}`, { ticks: BATCH, ...this.input() });
      this.buffer.push(...frames(this.start.header, got.frames));
      this.score = got.score;
    } catch (err) {
      this.failed = err instanceof Error ? err.message : String(err);
    } finally {
      this.asking = false;
      this.show();
    }
  }

  // what you're doing: keys, or walking to the spot under a held mouse button (the keys win)
  private input() {
    const on = (...keys: string[]) => keys.some((k) => this.held.has(k));
    let thrust = (on('w', 'arrowup') ? 1 : 0) - (on('s', 'arrowdown') ? 1 : 0);
    // the sim's turn is counterclockwise in its own x, y, which the viewer draws mirrored: on screen it turns right
    let turn = (on('d', 'arrowright') ? 1 : 0) - (on('a', 'arrowleft') ? 1 : 0);
    const me = this.last.creatures.find((c) => c.id === this.you);
    if (!thrust && !turn && this.pointer && me) {
      const box = this.canvas.getBoundingClientRect();
      this.caster.setFromCamera(new THREE.Vector2(((this.pointer.x - box.left) / box.width) * 2 - 1, -((this.pointer.y - box.top) / box.height) * 2 + 1), this.camera);
      const hit = this.caster.ray.intersectPlane(ground, new THREE.Vector3());
      if (hit) {
        const off = wrap(Math.atan2(hit.z - me.y, hit.x - me.x) - me.heading);
        const far = Math.hypot(hit.x - me.x, hit.z - me.y);
        turn = Math.max(-1, Math.min(1, off * 2));
        // turn on the spot to face it first, then walk, slowing as it gets there
        thrust = Math.abs(off) < 1.2 ? Math.min(1, far / 1.5) : 0;
      }
    }
    const yes = this.start.controls.filter((a) => ACTIONS[a] && on(...ACTIONS[a].keys));
    return { thrust, turn, yes };
  }

  private listen(): () => void {
    const down = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'shift', 'e', 'q', 'g', ' '].includes(key)) {
        this.held.add(key);
        if (key.startsWith('arrow') || key === ' ') e.preventDefault();
      }
    };
    const up = (e: KeyboardEvent) => this.held.delete(e.key.toLowerCase());
    // a window that loses focus never hears the keys come up
    const blur = () => this.held.clear();
    const press = (e: PointerEvent) => {
      if (e.button === 0) this.pointer = { x: e.clientX, y: e.clientY };
    };
    const move = (e: PointerEvent) => {
      if (this.pointer) this.pointer = { x: e.clientX, y: e.clientY };
    };
    const release = (e: PointerEvent) => {
      if (e.button === 0) this.pointer = null;
    };
    const menu = (e: Event) => e.preventDefault();
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    this.canvas.addEventListener('pointerdown', press);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', release);
    this.canvas.addEventListener('contextmenu', menu);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
      this.canvas.removeEventListener('pointerdown', press);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', release);
      this.canvas.removeEventListener('contextmenu', menu);
    };
  }

  private show() {
    const s = this.score;
    const you = s.you;
    const extra = this.start.controls.filter((a) => ACTIONS[a]).map((a) => `<b>${ACTIONS[a].label}</b> ${ACTIONS[a].what}`);
    const keys = ['<b>W A S D</b> or <b>arrows</b> walk and turn', '<b>hold the mouse</b> (or trackpad) to walk to a spot',
      ...extra, '<b>right-drag</b> look around', '<b>scroll</b> zoom', '<b>P</b> pause', '<b>R</b> new game'];
    let state: string;
    if (this.failed) state = `<p class="play-error">The game stopped: ${esc(this.failed)}. R starts a new one.</p>`;
    else if (s.over) {
      const food = you.per_minute > s.brain.per_minute ? 'You ate more a minute than the brain did.' : you.per_minute < s.brain.per_minute ? 'The brain ate more a minute than you.' : 'Level on food.';
      const lived = you.seconds > s.brain.seconds ? 'and you lived longer.' : you.seconds < s.brain.seconds ? 'and it lived longer.' : 'and you lived as long.';
      state = `<p class="play-over"><b>Game over.</b> ${food} ${lived} R plays again.</p>`;
    } else if (!you.alive) state = `<p class="play-over">You starved after ${you.seconds.toFixed(0)} s. Watching the rest; R plays again.</p>`;
    else state = '';
    this.panel.innerHTML = `
      <table>
        <tr><th></th><th>food a minute</th><th>alive</th></tr>
        <tr><td>You</td><td>${you.per_minute.toFixed(2)} <small>(${you.meals})</small></td><td>${you.seconds.toFixed(0)} s</td></tr>
        <tr><td>The brain</td><td>${s.brain.per_minute.toFixed(2)}</td><td>${s.brain.seconds.toFixed(0)} s <small>each</small></td></tr>
      </table>
      <div class="play-energy" title="energy"><span style="width:${Math.round((you.alive ? you.energy : 0) * 100)}%"></span></div>
      <p class="play-meta">${clock(s.seconds)} of ${clock(s.length)} · colonies ${s.colonies.join(' · ')}</p>
      ${state}
      <p class="play-keys">${keys.join(' · ')}</p>`;
  }
}
