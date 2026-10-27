// Little droppings left a while after eating. Viewer-only for now: the sim has
// no waste yet, so these follow real meals but nothing in the world reacts to them.
// Timed in sim ticks, so a replay leaves the same ones however fast it's played.

import * as THREE from 'three';
import type { CreatureState, Frame } from './world';

const MEALS = 3;
const DIGEST = 5; // seconds after the meal that fills the gut
const LIFE = 40; // seconds before it sinks into the lawn
const POP = 0.3;
const SINK = 2;
const BEHIND = 0.6; // the whole cluster clears the 0.45 m body
const SIZE = 0.6;

const pelletGeo = new THREE.SphereGeometry(1, 12, 8);
const pelletMat = new THREE.MeshPhysicalMaterial({ color: 0x5e4130, roughness: 0.75, sheen: 0.4, sheenColor: new THREE.Color(0x9c7458) });
const PELLETS: [number, number, number][] = [[-0.03, -0.06, 0.09], [0.09, -0.01, 0.075], [-0.06, 0.07, 0.068]];

function easeOutBack(t: number) {
  const c = 1.9;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
}

interface Dropping { root: THREE.Group; born: number }

export class Droppings {
  private gut = new Map<number, number>();
  private due: { id: number; at: number }[] = [];
  private live: Dropping[] = [];
  private lastTick = -1;

  constructor(private scene: THREE.Scene, private tickHz: number) {}

  meal(id: number, tick: number) {
    const meals = (this.gut.get(id) ?? 0) + 1;
    this.gut.set(id, meals % MEALS);
    if (meals === MEALS) this.due.push({ id, at: tick + Math.round(DIGEST * this.tickHz) });
  }

  push(frame: Frame) {
    if (frame.tick < this.lastTick) this.clear();
    this.lastTick = frame.tick;
    const byId = new Map(frame.creatures.map((c) => [c.id, c]));
    this.due = this.due.filter(({ id, at }) => {
      if (at > frame.tick) return true;
      const c = byId.get(id);
      if (c) this.drop(c, frame.tick);
      return false;
    });
    this.live = this.live.filter((d) => {
      const done = frame.tick - d.born > (LIFE + SINK) * this.tickHz;
      if (done) this.scene.remove(d.root);
      return !done;
    });
  }

  render(tick: number, alpha: number) {
    for (const d of this.live) {
      const age = (tick + alpha - d.born) / this.tickHz;
      const grow = age < POP ? easeOutBack(Math.max(0, age) / POP) : 1;
      const sink = Math.min(1, Math.max(0, (age - LIFE) / SINK));
      d.root.scale.setScalar(Math.max(0.001, SIZE * grow * (1 - sink * 0.6)));
      d.root.position.y = -sink * 0.08 * SIZE;
    }
  }

  clear() {
    for (const d of this.live) this.scene.remove(d.root);
    this.live = [];
    this.due = [];
    this.gut.clear();
  }

  private drop(c: CreatureState, tick: number) {
    const root = new THREE.Group();
    for (const [x, z, r] of PELLETS) {
      const m = new THREE.Mesh(pelletGeo, pelletMat);
      m.position.set(x, r * 0.75, z);
      m.scale.set(r, r * 0.8, r);
      m.castShadow = true;
      root.add(m);
    }
    root.position.set(c.x - Math.cos(c.heading) * BEHIND, 0, c.y - Math.sin(c.heading) * BEHIND);
    root.rotation.y = tick * 2.39;
    root.scale.setScalar(0.001);
    this.scene.add(root);
    this.live.push({ root, born: tick });
  }
}
