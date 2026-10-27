// A small tombstone where a Terrikin fell. The sim takes a dead body out of the
// world (nothing bumps into it or sees it), so the stone is only a marker: it
// stands a while, then fades. Timed in sim ticks, like droppings, so a replay
// leaves the same ones however fast it's played.

import * as THREE from 'three';
import { COLONY_COLOURS, GARDEN } from './palette';
import type { Frame } from './world';

const POP = 0.4;
const STAND = 20; // seconds before it starts to fade
const FADE = 10;

// a slab with a rounded top, bevelled so it reads as a toy rather than a grave
function slab() {
  const w = 0.17;
  const h = 0.26;
  const shape = new THREE.Shape();
  shape.moveTo(-w, 0);
  shape.lineTo(-w, h);
  shape.absarc(0, h, w, Math.PI, 0, true);
  shape.lineTo(w, 0);
  shape.lineTo(-w, 0);
  const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.06, bevelEnabled: true, bevelSize: 0.025, bevelThickness: 0.025, bevelSegments: 3, curveSegments: 16 });
  geo.translate(0, 0, -0.03);
  return geo;
}

const slabGeo = slab();
const moundGeo = new THREE.SphereGeometry(1, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2);
const beadGeo = new THREE.SphereGeometry(0.045, 12, 8);

interface Stone { root: THREE.Group; born: number; materials: THREE.MeshStandardMaterial[] }

export class Tombstones {
  private live: Stone[] = [];
  private dead = new Set<number>();
  private lastTick = -1;

  constructor(private scene: THREE.Scene, private tickHz: number) {}

  isDead(id: number) {
    return this.dead.has(id);
  }

  push(frame: Frame) {
    if (frame.tick < this.lastTick) this.clear();
    this.lastTick = frame.tick;
    for (const c of frame.creatures) {
      if (c.energy > 0) {
        // its arena started over
        this.dead.delete(c.id);
      } else if (!this.dead.has(c.id)) {
        this.dead.add(c.id);
        this.place(c.x, c.y, c.heading, c.colony, frame.tick);
      }
    }
    this.live = this.live.filter((s) => {
      const done = frame.tick - s.born > (STAND + FADE) * this.tickHz;
      if (done) this.remove(s);
      return !done;
    });
  }

  render(tick: number, alpha: number) {
    for (const s of this.live) {
      const age = (tick + alpha - s.born) / this.tickHz;
      const t = Math.min(1, Math.max(0, age) / POP);
      // rises out of the ground with a little overshoot
      s.root.scale.setScalar(Math.max(0.001, 1 + 2.2 * Math.pow(t - 1, 3) + 1.2 * Math.pow(t - 1, 2)));
      const fade = Math.min(1, Math.max(0, (age - STAND) / FADE));
      for (const m of s.materials) {
        m.opacity = 1 - fade;
        m.transparent = fade > 0;
      }
      s.root.visible = fade < 1;
    }
  }

  clear() {
    for (const s of this.live) this.remove(s);
    this.live = [];
    this.dead.clear();
  }

  private remove(s: Stone) {
    this.scene.remove(s.root);
    for (const m of s.materials) m.dispose();
  }

  private place(x: number, y: number, heading: number, colony: number, tick: number) {
    const stone = new THREE.MeshStandardMaterial({ color: 0xb9b4ad, roughness: 0.85 });
    const soil = new THREE.MeshStandardMaterial({ color: GARDEN.soil, roughness: 1 });
    const tint = new THREE.MeshStandardMaterial({ color: COLONY_COLOURS[colony % COLONY_COLOURS.length], roughness: 0.4 });
    const root = new THREE.Group();
    const mound = new THREE.Mesh(moundGeo, soil);
    mound.scale.set(0.3, 0.06, 0.22);
    mound.position.z = 0.12;
    mound.receiveShadow = true;
    const slabMesh = new THREE.Mesh(slabGeo, stone);
    slabMesh.castShadow = true;
    // its colony's colour, a bead set in the front like the one on its head
    const bead = new THREE.Mesh(beadGeo, tint);
    bead.position.set(0, 0.24, 0.06);
    root.add(mound, slabMesh, bead);
    root.position.set(x, 0, y);
    root.rotation.y = Math.PI / 2 - heading;
    root.scale.setScalar(0.001);
    this.scene.add(root);
    this.live.push({ root, born: tick, materials: [stone, soil, tint] });
  }
}
