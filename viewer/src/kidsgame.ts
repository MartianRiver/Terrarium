// A game of Catch them! on the kids server (sim kids.py, kidsserve.py), as a Source for the kids page: frames a few
// ticks ahead, each request carrying where you're steering. You steer by pointing: your Terrikin walks to wherever
// the mouse (or trackpad) is, no button needed, or a finger is, and keys and a gamepad's stick go by the screen, so
// they stay right as the camera turns. A click, Space, Shift or the pad's A, a bumper or the right trigger is the
// sprint where the world has one; with snacks it's turbo, held down while the bar lasts.
import * as THREE from 'three';
import type { Pad } from './kidspad';
import { parseReplay } from './replay';
import type { Frame, WorldInfo } from './world';

export interface Score {
  catches: number;
  seconds: number;
  length: number;
  over: boolean;
  pace: number;
  dizzy: number[];
  // on the floor now, and the turbo bar from 0 to 1 (little has them; big has none)
  snacks: Snack[];
  turbo: number;
}

export interface Snack {
  id: number;
  x: number;
  y: number;
  kind: 'berry' | 'seaweed';
}

export interface Catch {
  tick: number;
  id: number;
  x: number;
  y: number;
}

interface Start {
  game: string;
  header: unknown;
  frame: unknown;
  you: number;
  controls: string[];
  score: Score;
}

export type Device = 'mouse' | 'touch' | 'keys' | 'pad';

const AHEAD = 4;
const BATCH = 2;
const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const wrap = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));
const parse = (header: unknown, raw: unknown[]) => parseReplay([header, ...raw].map((x) => JSON.stringify(x)).join('\n'));
// yours is drawn in another colony's colour than the runners' (the one picked), so it stands out at a glance
const mark = (frames: Frame[], you: number, colour: number) => {
  for (const f of frames) for (const c of f.creatures) if (c.id === you) c.colony = colour;
  return frames;
};

async function post(url: string, body: object) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const got = await res.json().catch(() => null);
  if (!res.ok) throw new Error(got?.error ?? `the server said ${res.status}`);
  return got;
}

export class KidsGame {
  readonly info: WorldInfo;
  readonly you: number;
  readonly token: string;
  readonly canSprint: boolean;
  score: Score;
  failed = '';
  // the last way of steering used, said when the game ends
  device: Device;
  // false until the countdown's done: no frames are asked for
  going = false;
  private buffer: Frame[];
  private last: Frame;
  private asking = false;
  private catches: Catch[] = [];
  private held = new Set<string>();
  private point: { x: number; y: number } | null = null;
  private dash = false;
  // a mouse button held (or a second finger down): turbo runs while it's held
  private pressing = false;
  private caster = new THREE.Raycaster();
  private stop: () => void;

  private constructor(private start: Start, private camera: THREE.Camera, private canvas: HTMLCanvasElement, device: Device,
    private pad: Pad, private colour: number) {
    const { info, frames } = parse(start.header, [start.frame]);
    this.info = info;
    this.you = start.you;
    this.token = start.game;
    this.canSprint = start.controls.includes('sprint');
    this.buffer = mark(frames, start.you, colour);
    this.last = frames[0];
    this.score = start.score;
    this.device = device;
    this.stop = this.listen();
  }

  static async begin(mode: string, level: number, camera: THREE.Camera, canvas: HTMLCanvasElement, device: Device, pad: Pad, colour: number) {
    return new KidsGame(await post('/api/kids', { mode, level, device }), camera, canvas, device, pad, colour);
  }

  // the Source

  step(): Frame | null {
    const next = this.buffer.shift();
    if (next) this.last = next;
    void this.ask();
    return next ?? (this.score.over && !this.buffer.length ? null : this.last);
  }

  // over counts as ready, so the page steps on to the end
  ready(): boolean {
    void this.ask();
    return this.buffer.length > 0 || this.score.over;
  }

  label(): string {
    return '';
  }

  // the catches made up to this frame, for the page to celebrate as it draws them
  caughtBy(tick: number): Catch[] {
    const due = this.catches.filter((c) => c.tick <= tick);
    this.catches = this.catches.filter((c) => c.tick > tick);
    return due;
  }

  // why: the page went back to the start, or closed (a beacon, which still gets there as the page goes)
  end(why: 'home' | 'quit' | 'again') {
    this.stop();
    if (this.score.over) return;
    const body = JSON.stringify({ why });
    if (why === 'quit') navigator.sendBeacon(`/api/kids/${this.token}/end`, body);
    else void fetch(`/api/kids/${this.token}/end`, { method: 'POST', body }).catch(() => {});
  }

  private async ask() {
    if (!this.going || this.asking || this.score.over || this.failed || this.buffer.length >= AHEAD) return;
    this.asking = true;
    try {
      const got = await post(`/api/kids/${this.token}`, { ticks: BATCH, ...this.input() });
      this.buffer.push(...(got.frames.length ? mark(parse(this.start.header, got.frames).frames, this.you, this.colour) : []));
      this.catches.push(...got.events);
      this.score = got.score;
    } catch (err) {
      this.failed = err instanceof Error ? err.message : String(err);
    } finally {
      this.asking = false;
    }
  }

  private input() {
    const me = this.last.creatures.find((c) => c.id === this.you);
    let thrust = 0;
    let turn = 0;
    // turn to face the way wanted, walking all the while it's roughly ahead, so steering never feels stuck
    const towards = (x: number, z: number, far: number) => {
      if (!me || Math.hypot(x, z) < 1e-3) return;
      const off = wrap(Math.atan2(z, x) - me.heading);
      turn = Math.max(-1, Math.min(1, off * 2.5));
      thrust = Math.max(0, Math.cos(off)) * Math.min(1, far);
    };
    const pad = this.pad;
    if (pad.move.x || pad.move.y || pad.held('a') || pad.held('rt')) this.device = 'pad';
    const on = (...keys: string[]) => keys.some((k) => this.held.has(k));
    const up = (on('w', 'arrowup') ? 1 : 0) - (on('s', 'arrowdown') ? 1 : 0) - pad.move.y;
    const right = (on('d', 'arrowright') ? 1 : 0) - (on('a', 'arrowleft') ? 1 : 0) + pad.move.x;
    // keys or a stick take over from the pointer until it moves again: on a laptop the cursor is always somewhere
    // over the room, and yours would walk back to it the moment the stick was let go
    if (Math.hypot(up, right) > 0.2) {
      this.point = null;
      const ahead = this.camera.getWorldDirection(new THREE.Vector3()).setY(0).normalize();
      const side = new THREE.Vector3(-ahead.z, 0, ahead.x);
      const way = ahead.multiplyScalar(up).add(side.multiplyScalar(right));
      towards(way.x, way.z, Math.min(1, Math.hypot(up, right)));
    } else if (this.point && me) {
      const box = this.canvas.getBoundingClientRect();
      const at = new THREE.Vector2(((this.point.x - box.left) / box.width) * 2 - 1, -((this.point.y - box.top) / box.height) * 2 + 1);
      this.caster.setFromCamera(at, this.camera);
      const hit = this.caster.ray.intersectPlane(ground, new THREE.Vector3());
      // slowing only right at the spot, so it doesn't jitter round the pointer
      if (hit) towards(hit.x - me.x, hit.z - me.y, Math.hypot(hit.x - me.x, hit.z - me.y) / 0.6);
    }
    const sprint = this.canSprint && (this.dash || this.pressing || on(' ', 'shift') || pad.held('a') || pad.held('rt') || pad.held('rb') || pad.held('lb'));
    this.dash = false;
    return { thrust, turn, yes: sprint ? ['sprint'] : [] };
  }

  private listen(): () => void {
    const keys = ['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'shift', ' '];
    const down = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (!keys.includes(key)) return;
      this.held.add(key);
      this.device = 'keys';
      e.preventDefault();
    };
    const up = (e: KeyboardEvent) => this.held.delete(e.key.toLowerCase());
    const blur = () => {
      this.held.clear();
      this.pressing = false;
      this.point = null;
    };
    const move = (e: PointerEvent) => {
      // a finger only steers while it's down; a mouse steers wherever it is
      if (e.pointerType !== 'mouse' && !(e.buttons & 1)) return;
      this.point = { x: e.clientX, y: e.clientY };
      this.device = e.pointerType === 'mouse' ? 'mouse' : 'touch';
    };
    const press = (e: PointerEvent) => {
      move(e);
      if (e.pointerType === 'mouse' || !e.isPrimary) this.dash = this.pressing = true;
    };
    const lift = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' || !e.isPrimary) this.pressing = false;
      if (e.pointerType !== 'mouse' && e.isPrimary) this.point = null;
    };
    const left = (e: PointerEvent) => {
      if (e.pointerType === 'mouse') this.point = null;
    };
    const menu = (e: Event) => e.preventDefault();
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    window.addEventListener('pointermove', move);
    this.canvas.addEventListener('pointerdown', press);
    window.addEventListener('pointerup', lift);
    window.addEventListener('pointercancel', lift);
    document.documentElement.addEventListener('pointerleave', left);
    this.canvas.addEventListener('contextmenu', menu);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
      window.removeEventListener('pointermove', move);
      this.canvas.removeEventListener('pointerdown', press);
      window.removeEventListener('pointerup', lift);
      window.removeEventListener('pointercancel', lift);
      document.documentElement.removeEventListener('pointerleave', left);
      this.canvas.removeEventListener('contextmenu', menu);
    };
  }
}
