// Little droppings. In worlds with [dung] they're the sim's own, from each frame:
// they make whoever's near sick, and a Terrikin can carry one off. Elsewhere the
// viewer makes them up a while after real meals, for the look of it. Timed in sim
// ticks, so a replay leaves the same ones however fast it's played.

import * as THREE from 'three';
import type { CreatureState, DungState, Frame } from './world';

const MEALS = 3;
const DIGEST = 5; // seconds after the meal that fills the gut
const LIFE = 40; // seconds before it sinks into the lawn
const POP = 0.3;
const SINK = 2;
const BEHIND = 0.6; // the whole cluster clears the 0.45 m body
const SIZE = 0.6;
// the sim's are 0.15 m in radius, a heap you can see from across the arena
const REAL = 1.6;

const pelletGeo = new THREE.SphereGeometry(1, 12, 8);
const pelletMat = new THREE.MeshPhysicalMaterial({ color: 0x5e4130, roughness: 0.75, sheen: 0.4, sheenColor: new THREE.Color(0x9c7458) });
const PELLETS: [number, number, number][] = [[-0.03, -0.06, 0.09], [0.09, -0.01, 0.075], [-0.06, 0.07, 0.068]];

function easeOutBack(t: number) {
  const c = 1.9;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
}

interface Dropping { root: THREE.Group; born: number }

export function pellets(): THREE.Group {
  const root = new THREE.Group();
  for (const [x, z, r] of PELLETS) {
    const m = new THREE.Mesh(pelletGeo, pelletMat);
    m.position.set(x, r * 0.75, z);
    m.scale.set(r, r * 0.8, r);
    m.castShadow = true;
    root.add(m);
  }
  return root;
}

export class Droppings {
  private gut = new Map<number, number>();
  private due: { id: number; at: number }[] = [];
  private live: Dropping[] = [];
  // the sim's own, by id
  private real = new Map<number, Dropping>();
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
    if (frame.dung) {
      this.sync(frame.dung, frame.tick);
      return;
    }
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

  // what's lying now: new ones pop up, picked up or gone ones go
  private sync(lying: DungState[], tick: number) {
    const seen = new Set<number>();
    for (const { id, x, y } of lying) {
      seen.add(id);
      let d = this.real.get(id);
      if (!d) {
        d = { root: pellets(), born: tick };
        d.root.rotation.y = id * 2.39;
        d.root.scale.setScalar(0.001);
        this.scene.add(d.root);
        this.real.set(id, d);
      }
      d.root.position.set(x, 0, y);
    }
    for (const [id, d] of this.real) {
      if (seen.has(id)) continue;
      this.scene.remove(d.root);
      this.real.delete(id);
    }
  }

  render(tick: number, alpha: number) {
    for (const d of this.real.values()) {
      const age = (tick + alpha - d.born) / this.tickHz;
      d.root.scale.setScalar(Math.max(0.001, REAL * (age < POP ? easeOutBack(Math.max(0, age) / POP) : 1)));
    }
    for (const d of this.live) {
      const age = (tick + alpha - d.born) / this.tickHz;
      const grow = age < POP ? easeOutBack(Math.max(0, age) / POP) : 1;
      const sink = Math.min(1, Math.max(0, (age - LIFE) / SINK));
      d.root.scale.setScalar(Math.max(0.001, SIZE * grow * (1 - sink * 0.6)));
      d.root.position.y = -sink * 0.08 * SIZE;
    }
  }

  clear() {
    for (const d of [...this.live, ...this.real.values()]) this.scene.remove(d.root);
    this.live = [];
    this.real.clear();
    this.due = [];
    this.gut.clear();
  }

  private drop(c: CreatureState, tick: number) {
    const root = pellets();
    root.position.set(c.x - Math.cos(c.heading) * BEHIND, 0, c.y - Math.sin(c.heading) * BEHIND);
    root.rotation.y = tick * 2.39;
    root.scale.setScalar(0.001);
    this.scene.add(root);
    this.live.push({ root, born: tick });
  }
}
