// What a catch looks and sounds like in Catch them!: a burst of stars where it happened, stars circling the head of
// whoever's dizzy, and a boing. The sounds are made on the spot (Web Audio oscillators), so there are no files to
// load and nothing to license; quiet by design, since small children sit close to the speakers.
import * as THREE from 'three';
import type { Frame } from './world';

const STAR = '#ffd23f';
const BURST = 10;
const LIFE = 0.9;
const CIRCLE = 3;

function starTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d')!;
  g.translate(32, 32);
  g.beginPath();
  for (let i = 0; i < 10; i++) {
    const r = i % 2 ? 12 : 28;
    const a = (i / 10) * Math.PI * 2 - Math.PI / 2;
    g.lineTo(Math.cos(a) * r, Math.sin(a) * r);
  }
  g.closePath();
  g.fillStyle = STAR;
  g.strokeStyle = '#fff6d0';
  g.lineWidth = 4;
  g.fill();
  g.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

interface Spark {
  sprite: THREE.Sprite;
  vx: number;
  vy: number;
  vz: number;
  age: number;
}

export class CatchFx {
  private texture = starTexture();
  private sparks: Spark[] = [];
  private circling = new Map<number, THREE.Sprite[]>();
  private ring: { mesh: THREE.Mesh; age: number }[] = [];
  private ringGeo = new THREE.RingGeometry(0.8, 1, 40).rotateX(-Math.PI / 2);

  constructor(private scene: THREE.Scene) {}

  burst(x: number, y: number) {
    for (let i = 0; i < BURST; i++) {
      const sprite = this.star(0.7);
      sprite.position.set(x, 0.6, y);
      const a = (i / BURST) * Math.PI * 2 + Math.random() * 0.4;
      const out = 2 + Math.random() * 1.5;
      this.sparks.push({ sprite, vx: Math.cos(a) * out, vy: 3 + Math.random() * 2, vz: Math.sin(a) * out, age: 0 });
    }
    const mesh = new THREE.Mesh(this.ringGeo, new THREE.MeshBasicMaterial({ color: STAR, transparent: true, depthWrite: false }));
    mesh.position.set(x, 0.03, y);
    this.scene.add(mesh);
    this.ring.push({ mesh, age: 0 });
  }

  // dizzy: the ids spinning now; frame: where everyone is
  render(dt: number, time: number, frame: Frame | null, dizzy: number[]) {
    this.sparks = this.sparks.filter((s) => {
      s.age += dt;
      s.vy -= 9 * dt;
      s.sprite.position.x += s.vx * dt;
      s.sprite.position.y = Math.max(0.1, s.sprite.position.y + s.vy * dt);
      s.sprite.position.z += s.vz * dt;
      s.sprite.material.opacity = 1 - (s.age / LIFE) ** 2;
      if (s.age < LIFE) return true;
      this.scene.remove(s.sprite);
      s.sprite.material.dispose();
      return false;
    });
    this.ring = this.ring.filter((r) => {
      r.age += dt;
      const t = Math.min(r.age / 0.6, 1);
      r.mesh.scale.setScalar(0.3 + 1.4 * (1 - (1 - t) ** 3));
      (r.mesh.material as THREE.MeshBasicMaterial).opacity = 1 - t;
      if (t < 1) return true;
      this.scene.remove(r.mesh);
      (r.mesh.material as THREE.Material).dispose();
      return false;
    });
    for (const [id, stars] of this.circling) {
      if (dizzy.includes(id)) continue;
      for (const s of stars) {
        this.scene.remove(s);
        s.material.dispose();
      }
      this.circling.delete(id);
    }
    for (const id of dizzy) {
      const c = frame?.creatures.find((k) => k.id === id);
      if (!c) continue;
      let stars = this.circling.get(id);
      if (!stars) {
        stars = Array.from({ length: CIRCLE }, () => this.star(0.4));
        this.circling.set(id, stars);
      }
      stars.forEach((s, i) => {
        const a = time * 5 + (i / CIRCLE) * Math.PI * 2;
        s.position.set(c.x + Math.cos(a) * 0.45, 1.15 + Math.sin(a * 2) * 0.05, c.y + Math.sin(a) * 0.45);
      });
    }
  }

  // a honk: a ring of your colour spreading out from you
  honk(x: number, y: number) {
    const mesh = new THREE.Mesh(this.ringGeo, new THREE.MeshBasicMaterial({ color: '#7fd0ff', transparent: true, depthWrite: false }));
    mesh.position.set(x, 0.04, y);
    this.scene.add(mesh);
    this.ring.push({ mesh, age: 0 });
  }

  clear() {
    for (const s of this.sparks) this.scene.remove(s.sprite);
    for (const r of this.ring) this.scene.remove(r.mesh);
    for (const stars of this.circling.values()) for (const s of stars) this.scene.remove(s);
    this.sparks = [];
    this.ring = [];
    this.circling.clear();
  }

  private star(size: number) {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texture, transparent: true, depthWrite: false }));
    sprite.scale.setScalar(size);
    this.scene.add(sprite);
    return sprite;
  }
}

const KEY = 'terrarium.kids.sound';

export class Beeps {
  private ctx: AudioContext | null = null;
  private out: GainNode | null = null;
  on: boolean;

  constructor() {
    let on = true;
    try {
      on = localStorage.getItem(KEY) !== '0';
    } catch {
      // not remembered in a private window
    }
    this.on = on;
  }

  // browsers only make sound after a click or a key: call from one
  wake() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      const limit = this.ctx.createDynamicsCompressor();
      limit.connect(this.ctx.destination);
      this.out = this.ctx.createGain();
      this.out.gain.value = 0.35;
      this.out.connect(limit);
    }
    void this.ctx.resume();
  }

  toggle() {
    this.on = !this.on;
    try {
      localStorage.setItem(KEY, this.on ? '1' : '0');
    } catch {
      // as above
    }
  }

  boing() {
    this.tone({ from: 520 + Math.random() * 80, to: 140, length: 0.42, type: 'sine', wobble: 18, level: 0.9 });
    this.tone({ from: 1400, to: 900, length: 0.06, type: 'triangle', level: 0.4 });
  }

  // a bicycle-horn honk, two quick notes squeezed; a dragon gives a small growly roar instead
  honk(look = '') {
    if (look === 'dragon') {
      this.tone({ from: 260, to: 120, length: 0.5, type: 'sawtooth', wobble: 30, level: 0.22 });
      this.tone({ from: 520, to: 240, length: 0.35, type: 'triangle', level: 0.2, at: 0.03 });
      return;
    }
    this.tone({ from: 392, to: 370, length: 0.12, type: 'square', level: 0.25 });
    this.tone({ from: 494, to: 466, length: 0.16, type: 'square', level: 0.25, at: 0.13 });
  }

  count(last = false) {
    this.tone({ from: last ? 880 : 520, to: last ? 880 : 520, length: last ? 0.45 : 0.16, type: 'triangle', level: 0.7 });
  }

  tick() {
    this.tone({ from: 1200, to: 700, length: 0.05, type: 'square', level: 0.15 });
  }

  // up the notes, and once more at the top for a new best
  fanfare(best: boolean) {
    const notes = best ? [523, 659, 784, 1047, 1319] : [523, 659, 784, 1047];
    notes.forEach((f, i) => this.tone({ from: f, to: f, length: 0.22, type: 'triangle', level: 0.6, at: i * 0.13 }));
  }

  private tone(o: { from: number; to: number; length: number; type: OscillatorType; level: number; wobble?: number; at?: number }) {
    if (!this.on || !this.ctx || !this.out || document.hidden) return;
    const ctx = this.ctx;
    const t = ctx.currentTime + (o.at ?? 0);
    const osc = new OscillatorNode(ctx, { type: o.type, frequency: o.from });
    osc.frequency.setValueAtTime(o.from, t);
    osc.frequency.exponentialRampToValueAtTime(Math.max(o.to, 1), t + o.length);
    if (o.wobble) {
      const lfo = new OscillatorNode(ctx, { frequency: 14 });
      const depth = new GainNode(ctx, { gain: o.wobble });
      lfo.connect(depth).connect(osc.frequency);
      lfo.start(t);
      lfo.stop(t + o.length);
    }
    const gain = new GainNode(ctx, { gain: 0 });
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(o.level, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, t + o.length);
    osc.connect(gain).connect(this.out);
    osc.start(t);
    osc.stop(t + o.length + 0.02);
  }
}
