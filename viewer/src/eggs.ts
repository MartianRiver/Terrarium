// Eggs on a nest, from the replay's `eggs` (worlds with hatching). An egg sits
// where its Terrikin will hatch, rocks more as it gets close, then cracks: the
// shell's two halves spring apart and fade, and the hatchling (which takes the
// egg's id) swells from small to full size. An egg that goes without hatching
// (its colony died out) just shrinks away. Timed in sim ticks, like
// tombstones, so a replay looks the same however fast it's played.

import * as THREE from 'three';
import { COLONY_COLOURS } from './palette';
import type { EggState, Frame } from './world';

const SHELL = 0xf4ecdc;
const HEIGHT = 0.3;
const CRACK = 0.7; // seconds the shell halves take to fly and fade
const GROW = 1.4; // seconds a hatchling takes to reach full size
const SMALL = 0.35; // its size as it comes out, of a grown one's
const ROCK = 0.6; // progress after which it starts to rock

// an egg's outline turned on the lathe: fuller at the bottom
function eggPoints(from: number, to: number) {
  const points: THREE.Vector2[] = [];
  for (let i = 0; i <= 24; i++) {
    const t = from + ((to - from) * i) / 24;
    const y = (1 - Math.cos(Math.PI * t)) / 2;
    const r = Math.sin(Math.PI * t) * (0.62 - 0.12 * y) * HEIGHT;
    points.push(new THREE.Vector2(Math.max(r, 1e-4), y * HEIGHT));
  }
  return points;
}

const SPLIT = 0.55;
// where the shell splits, in metres up the egg
const SPLIT_Y = ((1 - Math.cos(Math.PI * SPLIT)) / 2) * HEIGHT;
const wholeGeo = new THREE.LatheGeometry(eggPoints(0, 1), 24);
const bottomGeo = new THREE.LatheGeometry(eggPoints(0, SPLIT), 24);
// the top half pivots on its own rim
const topGeo = new THREE.LatheGeometry(eggPoints(SPLIT, 1), 24).translate(0, -SPLIT_Y, 0);
const speckGeo = new THREE.SphereGeometry(0.018, 8, 6);
for (const g of [wholeGeo, bottomGeo, topGeo]) g.computeVertexNormals();

interface Egg { root: THREE.Group; shell: THREE.MeshStandardMaterial; speck: THREE.MeshStandardMaterial; tilt: number }
interface Crack { top: THREE.Mesh; bottom: THREE.Mesh; tick: number; materials: THREE.MeshStandardMaterial[]; root: THREE.Group }

export class Eggs {
  private eggs = new Map<number, Egg>();
  private going: { egg: Egg; tick: number }[] = [];
  private cracks: Crack[] = [];
  // hatchlings by id, and the tick each came out
  private hatched = new Map<number, number>();
  private lastTick = -1;

  constructor(private scene: THREE.Scene, private tickHz: number) {}

  push(frame: Frame) {
    if (frame.tick < this.lastTick) this.clear();
    this.lastTick = frame.tick;
    const now = new Map(frame.eggs.map((e) => [e.id, e]));
    for (const e of frame.eggs) {
      if (!this.eggs.has(e.id)) this.eggs.set(e.id, this.lay(e));
      this.eggs.get(e.id)!.root.userData.progress = e.progress;
    }
    const born = new Set(frame.creatures.map((c) => c.id));
    for (const [id, egg] of this.eggs) {
      if (now.has(id)) continue;
      this.eggs.delete(id);
      if (born.has(id)) {
        this.hatched.set(id, frame.tick);
        this.crack(egg, frame.tick);
      } else {
        this.going.push({ egg, tick: frame.tick });
      }
    }
  }

  // how big a creature is drawn, as a share of its size: under 1 while it's just hatched
  growth(id: number, tick: number, alpha: number) {
    const at = this.hatched.get(id);
    if (at === undefined) return 1;
    const t = (tick + alpha - at) / this.tickHz / GROW;
    if (t >= 1) {
      this.hatched.delete(id);
      return 1;
    }
    // springs a little past full size before it settles
    const eased = 1 + 2.2 * Math.pow(t - 1, 3) + 1.2 * Math.pow(t - 1, 2);
    return SMALL + (1 - SMALL) * Math.max(0, eased);
  }

  render(tick: number, alpha: number, time: number) {
    for (const egg of this.eggs.values()) {
      const p = egg.root.userData.progress as number;
      const rock = Math.max(0, (p - ROCK) / (1 - ROCK));
      egg.root.rotation.z = egg.tilt + rock * 0.25 * Math.sin(time * (6 + 10 * rock));
      egg.root.rotation.x = rock * 0.12 * Math.sin(time * 9.3 + 1);
      // pops in when laid
      egg.root.scale.setScalar(Math.min(1, 0.2 + 4 * Math.max(0, p)));
    }
    this.going = this.going.filter(({ egg, tick: at }) => {
      const t = (tick + alpha - at) / this.tickHz / 0.5;
      egg.root.scale.setScalar(Math.max(0.001, 1 - t));
      if (t < 1) return true;
      this.drop(egg.root, [egg.shell, egg.speck]);
      return false;
    });
    this.cracks = this.cracks.filter((c) => {
      const t = (tick + alpha - c.tick) / this.tickHz / CRACK;
      c.top.position.set(0.18 * t, SPLIT_Y + HEIGHT * (1.2 * t - 1.6 * t * t), 0);
      c.top.rotation.z = -1.8 * t;
      c.bottom.position.x = -0.1 * t;
      c.bottom.rotation.z = 0.6 * t;
      for (const m of c.materials) {
        m.transparent = true;
        m.opacity = Math.max(0, 1 - t * t);
      }
      if (t < 1) return true;
      this.drop(c.root, c.materials);
      return false;
    });
  }

  clear() {
    for (const egg of this.eggs.values()) this.drop(egg.root, [egg.shell, egg.speck]);
    for (const { egg } of this.going) this.drop(egg.root, [egg.shell, egg.speck]);
    for (const c of this.cracks) this.drop(c.root, c.materials);
    this.eggs.clear();
    this.going = [];
    this.cracks = [];
    this.hatched.clear();
  }

  get count() {
    return this.eggs.size;
  }

  private lay(e: EggState): Egg {
    const shell = new THREE.MeshStandardMaterial({ color: SHELL, roughness: 0.5 });
    const speck = new THREE.MeshStandardMaterial({ color: COLONY_COLOURS[e.colony % COLONY_COLOURS.length], roughness: 0.6 });
    const root = new THREE.Group();
    const body = new THREE.Mesh(wholeGeo, shell);
    body.castShadow = true;
    root.add(body);
    // its colony's colour in a few specks, set by its id so it looks the same every time
    for (let i = 0; i < 7; i++) {
      const a = (e.id * 2.39996 + i * 2.39996) % (Math.PI * 2);
      const y = 0.2 + 0.6 * (((e.id * 7 + i * 13) % 10) / 10);
      const r = Math.sin(Math.PI * y) * (0.62 - 0.12 * y) * HEIGHT;
      const s = new THREE.Mesh(speckGeo, speck);
      s.position.set(Math.cos(a) * r, y * HEIGHT, Math.sin(a) * r);
      root.add(s);
    }
    root.position.set(e.x, 0, e.y);
    const tilt = (((e.id * 37) % 11) / 11 - 0.5) * 0.2;
    root.scale.setScalar(0.2);
    this.scene.add(root);
    return { root, shell, speck, tilt };
  }

  private crack(egg: Egg, tick: number) {
    const root = new THREE.Group();
    root.position.copy(egg.root.position);
    root.rotation.y = egg.root.rotation.y;
    const shell = egg.shell.clone();
    const top = new THREE.Mesh(topGeo, shell);
    const bottom = new THREE.Mesh(bottomGeo, shell);
    top.position.y = SPLIT_Y;
    root.add(top, bottom);
    this.scene.add(root);
    this.drop(egg.root, [egg.shell, egg.speck]);
    this.cracks.push({ top, bottom, tick, materials: [shell], root });
  }

  private drop(root: THREE.Group, materials: THREE.Material[]) {
    this.scene.remove(root);
    for (const m of materials) m.dispose();
  }
}
