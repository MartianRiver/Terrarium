// Nectar flowers, from a frame's `flowers`: a stem with a bud that unfolds into
// lorikeet-coloured petals around a shimmering drop of nectar, and folds shut
// and sinks away when it's drunk or wilts. Timed in sim ticks like the eggs.

import * as THREE from 'three';
import { LORIKEET, shimmer } from './palette';
import type { FlowerState, Frame } from './world';

const OPEN = 1.0; // seconds to unfold
const CLOSE = 0.8; // seconds to fold shut and sink
const HEAD = 0.42;
const PETALS = 6;
// drawn bigger than a berry, so it shows from the overview
const SIZE = 1.5;

const stemGeo = new THREE.CylinderGeometry(0.018, 0.026, HEAD, 6).translate(0, HEAD / 2, 0);
const leafGeo = new THREE.SphereGeometry(0.1, 8, 6).scale(1, 0.25, 1.9).translate(0, 0, 0.16);
// rooted at the middle of the flower, so it opens like a hinge
const petalGeo = new THREE.SphereGeometry(1, 12, 8).scale(0.17, 0.035, 0.09).translate(0.17, 0, 0);
const dropGeo = new THREE.SphereGeometry(0.075, 16, 12);
const green = new THREE.MeshStandardMaterial({ color: 0x4f9f45, roughness: 0.7 });
const petalMats = LORIKEET.map((c) => new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.45, sheen: 0.6, emissive: c, emissiveIntensity: 0.22 }));
// a soft glow round the flower's head, tinted with the nectar
const haloTex = (() => {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d')!;
  const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, 'rgba(255,255,255,0.9)');
  r.addColorStop(0.35, 'rgba(255,255,255,0.35)');
  r.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = r;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();

interface Flower { root: THREE.Group; head: THREE.Group; petals: THREE.Group[]; drop: THREE.Mesh; mat: THREE.MeshStandardMaterial; halo: THREE.Sprite; born: number; seed: number }

export class Flowers {
  private flowers = new Map<number, Flower>();
  private closing: { f: Flower; tick: number }[] = [];
  private lastTick = -1;

  constructor(private scene: THREE.Scene, private tickHz: number) {}

  push(frame: Frame) {
    if (frame.tick < this.lastTick) this.clear();
    this.lastTick = frame.tick;
    const now = new Map(frame.flowers.map((f) => [f.id, f]));
    for (const f of now.values()) if (!this.flowers.has(f.id)) this.flowers.set(f.id, this.grow(f, frame.tick));
    for (const [id, f] of this.flowers) {
      if (now.has(id)) continue;
      this.flowers.delete(id);
      this.closing.push({ f, tick: frame.tick });
    }
  }

  render(tick: number, alpha: number, time: number) {
    for (const f of this.flowers.values()) {
      const t = Math.min(1, (tick + alpha - f.born) / this.tickHz / OPEN);
      this.pose(f, t, time);
      f.root.scale.setScalar(SIZE * Math.min(1, 0.3 + t * 1.5));
    }
    this.closing = this.closing.filter(({ f, tick: at }) => {
      const t = Math.min(1, (tick + alpha - at) / this.tickHz / CLOSE);
      this.wilt(f, t);
      if (t < 1) return true;
      this.drop(f);
      return false;
    });
  }

  clear() {
    for (const f of this.flowers.values()) this.drop(f);
    for (const { f } of this.closing) this.drop(f);
    this.flowers.clear();
    this.closing = [];
  }

  // open: 0 a closed bud, 1 petals spread
  private pose(f: Flower, open: number, time: number) {
    const eased = 1 - (1 - open) ** 3;
    for (const p of f.petals) p.rotation.z = 1.35 - eased * 1.2;
    f.drop.scale.setScalar(eased * (1 + Math.sin(time * 4 + f.seed) * 0.08));
    shimmer(time, f.seed, f.mat.color);
    f.mat.emissive.copy(f.mat.color);
    const glow = f.halo.material;
    glow.color.copy(f.mat.color);
    glow.opacity = eased * (0.45 + Math.sin(time * 2.5 + f.seed) * 0.12);
    f.halo.scale.setScalar(0.25 + eased * 0.55);
    f.head.rotation.y = Math.sin(time * 0.8 + f.seed) * 0.15;
  }

  // emptied: the nectar and its glow go at once, the petals droop, and it shrinks into the grass
  private wilt(f: Flower, t: number) {
    const fast = Math.min(1, t * 5);
    f.drop.scale.setScalar(Math.max(0.001, 1 - fast));
    f.halo.material.opacity *= 1 - fast;
    const droop = t * t * (3 - 2 * t);
    for (const p of f.petals) p.rotation.z = 0.15 - droop * 0.9;
    f.head.rotation.x = droop * 0.5;
    f.root.scale.setScalar(SIZE * Math.max(0.001, 1 - Math.max(0, t - 0.4) / 0.6));
  }

  private grow(s: FlowerState, tick: number): Flower {
    const root = new THREE.Group();
    root.position.set(s.x, 0, s.y);
    const seed = (s.id * 1.618) % 6;
    root.rotation.y = seed;
    const stem = new THREE.Mesh(stemGeo, green);
    stem.castShadow = true;
    root.add(stem);
    for (const side of [-1, 1]) {
      const leaf = new THREE.Mesh(leafGeo, green);
      leaf.position.y = 0.08 + (side + 1) * 0.04;
      leaf.rotation.set(0.5, side * 1.4, 0);
      root.add(leaf);
    }
    const head = new THREE.Group();
    head.position.y = HEAD;
    const petals: THREE.Group[] = [];
    for (let i = 0; i < PETALS; i++) {
      const hinge = new THREE.Group();
      hinge.rotation.y = (i / PETALS) * Math.PI * 2;
      const pivot = new THREE.Group();
      const petal = new THREE.Mesh(petalGeo, petalMats[(i + s.id) % petalMats.length]);
      petal.castShadow = true;
      pivot.add(petal);
      hinge.add(pivot);
      head.add(hinge);
      petals.push(pivot);
    }
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.15, emissiveIntensity: 1.4 });
    const drop = new THREE.Mesh(dropGeo, mat);
    drop.position.y = 0.03;
    head.add(drop);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    halo.position.y = 0.04;
    head.add(halo);
    root.add(head);
    root.scale.setScalar(SIZE * 0.3);
    this.scene.add(root);
    return { root, head, petals, drop, mat, halo, born: tick, seed };
  }

  private drop(f: Flower) {
    this.scene.remove(f.root);
    f.mat.dispose();
    f.halo.material.dispose();
  }
}
