// Play as one Terrikin (local only, ?play[=run id]): a game on the runs server (sim play.py) in a run's world, the
// rest steered by its newest brain. Frames come a few ticks at a time, each request carrying what you're doing, so
// the game runs at the viewer's pace and stops when it pauses. A bar along the top shows your energy and points, and a
// panel the controls this world has and how you're doing next to the brain's worst, average and best Terrikins. Under
// the bar, what's hard to see on the body (a full crop, the sprint's rest, nectar, nightfall), with a word as each changes.
import * as THREE from 'three';
import { clock } from './clock';
import { parseReplay } from './replay';
import type { Frame, WorldInfo } from './world';

interface Card {
  seconds: number;
  berries: number;
  home: number;
  points: number;
}

// what the world has: no sprint, carry or night in the state means the world hasn't got them
interface State {
  crop: number;
  capacity: number;
  store: number;
  home: boolean;
  hungry: boolean;
  turbo: number;
  carrying?: boolean;
  sprint?: { left: number; rest: number };
  night?: { dark: boolean; in: number };
}

interface Score {
  you: Card & { alive: boolean; energy: number; state: State };
  // empty in a world of one
  brain: { worst?: Card; average?: Card; best?: Card; count?: number };
  rank: number;
  points: { second: number; berry: number; home: number };
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

const CHASE = 'terrarium.play.chase';
const remembered = () => {
  try {
    return localStorage.getItem(CHASE) === '1';
  } catch {
    return false;
  }
};

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
  // C: walk towards the mouse wherever it is, no button held, as in agar.io
  private chase = remembered();
  private hover: { x: number; y: number } | null = null;
  private chaseButton = document.createElement('button');
  private caster = new THREE.Raycaster();
  private panel: HTMLElement;
  private hud: HTMLElement;
  private before: Card | null = null;
  // when each counter last went up, so it stays lit a moment (the panel is redrawn every few ticks)
  private lit: Partial<Record<keyof Card, number>> = {};
  private was: State | null = null;
  private wasEnergy = 1;
  private toasts: HTMLElement;
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
    this.hud = document.createElement('div');
    this.hud.id = 'play-hud';
    // built once and only updated, so the bar slides and a low one keeps pulsing
    this.hud.innerHTML = `
      <div class="hud-energy"><span class="hud-label">Energy</span><span class="hud-bar"><span></span></span><span class="hud-value"></span></div>
      <div class="hud-points"><span class="hud-label">Score</span><b></b></div>
      <div class="hud-counts"><span data-k="seconds"></span><span data-k="berries"></span><span data-k="home"></span></div>
      <div class="hud-state"><span class="hud-sprint"><span class="hud-label">Sprint</span><span class="hud-bar"><span></span></span><i></i></span><span class="hud-chips"></span></div>`;
    this.chaseButton.type = 'button';
    this.chaseButton.className = 'hud-chase';
    this.chaseButton.addEventListener('click', () => this.setChase(!this.chase));
    this.hud.querySelector('.hud-state')!.append(this.chaseButton);
    this.setChase(this.chase);
    this.toasts = document.createElement('div');
    this.toasts.id = 'play-toasts';
    document.body.append(this.panel, this.hud, this.toasts);
    this.stop = this.listen();
    this.show();
  }

  // invite: the hosted play server's (playserve.py), which plays one brain and wants no run
  static async begin(run: string | null, camera: THREE.Camera, canvas: HTMLCanvasElement, invite: string | null = null): Promise<Game> {
    return new Game(await post('/api/play', invite ? { invite } : run ? { run } : {}), camera, canvas);
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
    this.hud.remove();
    this.toasts.remove();
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

  // what you're doing: keys, or walking to the spot under a held mouse button, or under the mouse with C on (the keys win). Keys go by the
  // screen, whichever way the camera faces: W is up the screen, D is right, and two together go between
  private input() {
    const on = (...keys: string[]) => keys.some((k) => this.held.has(k));
    const up = (on('w', 'arrowup') ? 1 : 0) - (on('s', 'arrowdown') ? 1 : 0);
    const right = (on('d', 'arrowright') ? 1 : 0) - (on('a', 'arrowleft') ? 1 : 0);
    const me = this.last.creatures.find((c) => c.id === this.you);
    let thrust = 0;
    let turn = 0;
    // sim x, y are the viewer's x, z: turn to face the way wanted, walking once roughly facing it
    const towards = (x: number, z: number, far: number) => {
      if (!me) return;
      const off = wrap(Math.atan2(z, x) - me.heading);
      turn = Math.max(-1, Math.min(1, off * 2));
      thrust = Math.abs(off) < 1.2 ? Math.min(1, far) : 0;
    };
    if (up || right) {
      const ahead = this.camera.getWorldDirection(new THREE.Vector3()).setY(0).normalize();
      const side = new THREE.Vector3(-ahead.z, 0, ahead.x);
      const way = ahead.multiplyScalar(up).add(side.multiplyScalar(right));
      towards(way.x, way.z, 1);
    } else if ((this.pointer || (this.chase && this.hover)) && me) {
      const at = (this.pointer ?? this.hover)!;
      const box = this.canvas.getBoundingClientRect();
      this.caster.setFromCamera(new THREE.Vector2(((at.x - box.left) / box.width) * 2 - 1, -((at.y - box.top) / box.height) * 2 + 1), this.camera);
      const hit = this.caster.ray.intersectPlane(ground, new THREE.Vector3());
      // slowing as it gets there
      if (hit) towards(hit.x - me.x, hit.z - me.y, Math.hypot(hit.x - me.x, hit.z - me.y) / 1.5);
    }
    const yes = this.start.controls.filter((a) => ACTIONS[a] && on(...ACTIONS[a].keys));
    return { thrust, turn, yes };
  }

  private listen(): () => void {
    const down = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (key === 'c' && !e.repeat) this.setChase(!this.chase);
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
      // a mouse only: a finger lifted is no place to walk to
      if (e.pointerType === 'mouse') this.hover = { x: e.clientX, y: e.clientY };
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

  private setChase(on: boolean) {
    this.chase = on;
    this.chaseButton.textContent = on ? 'Following the mouse' : 'Follow the mouse';
    this.chaseButton.setAttribute('aria-pressed', String(on));
    this.chaseButton.title = 'C turns it on and off';
    try {
      localStorage.setItem(CHASE, on ? '1' : '0');
    } catch {
      // not remembered in a private window
    }
  }

  private show() {
    const s = this.score;
    const you = s.you;
    const extra = this.start.controls.filter((a) => ACTIONS[a]).map((a) => `<b>${ACTIONS[a].label}</b> ${ACTIONS[a].what}`);
    const keys = ['<b>W A S D</b> or <b>arrows</b> walk and turn', '<b>hold the mouse</b> (or trackpad) to walk to a spot',
      '<b>C</b> follow the mouse without holding',
      ...extra, '<b>right-drag</b> look around', '<b>scroll</b> zoom', '<b>P</b> pause', '<b>R</b> new game'];
    const { worst, average, best, count } = s.brain;
    let state: string;
    if (this.failed) state = `<p class="play-error">The game stopped: ${esc(this.failed)}. R starts a new one.</p>`;
    else if (s.over || !you.alive) {
      const how = !best || !worst || !average ? ''
        : you.points > best.points ? 'You beat every one of the brain\'s Terrikins!'
        : you.points >= average.points ? 'Better than the brain\'s average.'
        : you.points >= worst.points ? 'Below the brain\'s average.'
        : 'Even the brain\'s worst did better.';
      const first = s.over ? '<b>Game over.</b>' : `You starved after ${you.seconds.toFixed(0)} s.`;
      state = `<p class="play-over">${first} ${how} ${s.over ? 'R plays again.' : 'Watching the rest; R plays again.'}</p>`;
    } else state = '';
    const row = (name: string, c: Card | undefined, cls = '') => c
      ? `<tr class="${cls}"><td>${name}</td><td><b>${Math.round(c.points)}</b></td><td>${c.seconds.toFixed(0)} s</td><td>${c.berries.toFixed(c === average ? 1 : 0)}</td><td>${c.home.toFixed(c === average ? 1 : 0)}</td></tr>`
      : '';
    const p = s.points;
    this.panel.innerHTML = `
      <table>
        <tr><th></th><th>points</th><th>alive</th><th>berries</th><th>home</th></tr>
        ${row('You', you, 'play-you')}
        ${row('Brain\'s best', best)}
        ${row('Brain\'s average', average)}
        ${row('Brain\'s worst', worst)}
      </table>
      ${count ? `<p class="play-rank">You're <b>${ordinal(s.rank)}</b> of ${count + 1} that started.</p>` : ''}
      <p class="play-meta">${p.second} point a second alive · ${p.berry} a berry picked up · ${p.home} a food brought home · ${clock(s.seconds)} of ${clock(s.length)} · colonies ${s.colonies.join(' · ')}</p>
      ${state}
      <p class="play-keys">${keys.join(' · ')}</p>`;
    // a counter that just went up lights up for a moment
    const now = performance.now();
    for (const k of ['berries', 'home', 'points'] as const) {
      if (this.before && you[k] > this.before[k] + (k === 'points' ? 5 : 0)) this.lit[k] = now;
    }
    const bump = (k: keyof Card) => (now - (this.lit[k] ?? -1e9) < 600 ? ' bump' : '');
    const energy = Math.round((you.alive ? you.energy : 0) * 100);
    const bar = this.hud.querySelector<HTMLElement>('.hud-energy')!;
    bar.className = `hud-energy ${energy > 50 ? 'high' : energy > 25 ? 'mid' : 'low'}`;
    bar.querySelector<HTMLElement>('.hud-bar span')!.style.width = `${energy}%`;
    bar.querySelector('.hud-value')!.textContent = `${energy}%`;
    const points = this.hud.querySelector<HTMLElement>('.hud-points')!;
    points.className = `hud-points${bump('points')}`;
    points.querySelector('b')!.textContent = String(Math.round(you.points));
    const counts: Record<string, string> = { seconds: `${clock(you.seconds)} <small>alive</small>`,
      berries: `${you.berries} <small>berries</small>`, home: `${you.home} <small>brought home</small>` };
    for (const span of this.hud.querySelectorAll<HTMLElement>('.hud-counts span[data-k]')) {
      const k = span.dataset.k as keyof Card;
      span.innerHTML = counts[k];
      span.className = bump(k).trim();
    }
    this.before = { seconds: you.seconds, berries: you.berries, home: you.home, points: you.points };
    this.assist(you.state, you.alive ? energy : -1);
  }

  // the state line under the bar, and a word when something changes
  private assist(st: State, energy: number) {
    const line = this.hud.querySelector<HTMLElement>('.hud-state')!;
    line.hidden = energy < 0;
    if (energy < 0) return;
    const sprint = this.hud.querySelector<HTMLElement>('.hud-sprint')!;
    sprint.hidden = !st.sprint;
    if (st.sprint) {
      const { left, rest } = st.sprint;
      const fill = left > 0 ? left : 1 - rest;
      sprint.className = `hud-sprint ${left > 0 ? 'going' : rest > 0 ? 'resting' : 'ready'}`;
      sprint.querySelector<HTMLElement>('.hud-bar span')!.style.width = `${Math.round(fill * 100)}%`;
      sprint.querySelector('i')!.textContent = left > 0 ? 'go!' : rest > 0 ? 'resting' : 'ready';
    }
    const chips: string[] = [];
    if (st.capacity > 0) {
      const dots = '●'.repeat(st.crop) + '○'.repeat(Math.max(st.capacity - st.crop, 0));
      chips.push(`<span class="${st.crop >= st.capacity ? 'full' : ''}">Jelly belly ${dots}${st.crop >= st.capacity ? ' full' : ''}</span>`);
    }
    if (st.carrying) chips.push('<span>Carrying a berry</span>');
    if (st.turbo > 0) chips.push(`<span class="turbo">Turbo ${Math.ceil(st.turbo)} s</span>`);
    if (st.home) {
      const can = [st.crop > 0 && this.has('unload') ? '<b>Q</b> unload' : '',
        st.hungry && st.crop === 0 && st.store > 0 && this.has('eat') ? '<b>E</b> eat a jelly' : ''].filter(Boolean);
      chips.push(`<span class="home">Home · ${st.store} jelly stored${can.length ? ' · ' + can.join(' · ') : ''}</span>`);
    }
    if (st.night) chips.push(st.night.dark ? `<span class="night">Night · dawn in ${Math.ceil(st.night.in)} s</span>`
      : st.night.in <= 15 ? `<span class="dusk">Night in ${Math.ceil(st.night.in)} s</span>` : '');
    const html = chips.join('');
    const box = this.hud.querySelector<HTMLElement>('.hud-chips')!;
    // only when it changes, so the chips don't flicker
    if (box.innerHTML !== html) box.innerHTML = html;
    const was = this.was;
    if (was) {
      if (st.capacity > 0 && st.crop >= st.capacity && was.crop < st.capacity)
        this.toast(this.has('unload') ? 'Jelly belly full! Take it home (Q unloads)' : 'Jelly belly full!');
      if (st.sprint && was.sprint && was.sprint.rest > 0 && st.sprint.rest === 0 && st.sprint.left === 0) this.toast('Sprint ready (Shift)', 'quiet');
      if (st.turbo > 0 && was.turbo === 0) this.toast('Nectar! Turbo mode', 'turbo');
      if (st.night && was.night && !st.night.dark && st.night.in <= 15 && was.night.in > 15) this.toast('Night in 15 s: get home, the dark is cold', 'dusk');
      if (st.night && was.night && st.night.dark && !was.night.dark) this.toast('Night: no food grows till dawn', 'dusk');
      if (st.home && !was.home && st.hungry && st.crop === 0 && st.store > 0 && this.has('eat')) this.toast('Hungry? E eats a jelly from the store', 'quiet');
    }
    if (energy <= 25 && this.wasEnergy > 25) this.toast('Low energy: eat something!', 'low');
    this.was = st;
    this.wasEnergy = energy;
  }

  private has(action: string): boolean {
    return this.start.controls.includes(action);
  }

  private toast(text: string, kind = '') {
    const el = document.createElement('div');
    el.className = `play-toast ${kind}`;
    el.textContent = text;
    this.toasts.append(el);
    // a few at most, newest at the bottom
    while (this.toasts.children.length > 3) this.toasts.firstElementChild!.remove();
    setTimeout(() => el.remove(), 2600);
  }
}

function ordinal(n: number): string {
  const tens = n % 100;
  const end = tens >= 11 && tens <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${end}`;
}
