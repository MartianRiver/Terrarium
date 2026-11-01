// The snacks on the floor in Catch them!'s little room (sim kids.py): berries and sheets of seaweed, the same to the
// game and only drawn differently. Each pops up when it's put down, bobs so it's easy to spot, and when it's gone
// (eaten) says where, for a crunch and a puff.
import * as THREE from 'three';
import { berryGeo, berryMat, leafGeo, leafMat } from './props';
import type { Snack } from './kidsgame';

const POP = 0.35;
const SIZE = 2.4;

const noriMat = new THREE.MeshPhysicalMaterial({ color: 0x24402a, roughness: 0.55, sheen: 0.8, sheenColor: new THREE.Color(0x6f9d6a), side: THREE.DoubleSide });
const glowMat = new THREE.MeshBasicMaterial({ color: 0xfff3a0, transparent: true, opacity: 0.35, depthWrite: false });
const glowGeo = new THREE.CircleGeometry(0.42, 32).rotateX(-Math.PI / 2);

// a crinkled sheet, as roasted seaweed comes
function sheetGeo() {
  const g = new THREE.PlaneGeometry(0.24, 0.18, 12, 8).rotateX(-Math.PI / 2);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) p.setY(i, Math.sin(p.getX(i) * 70) * 0.004 + Math.sin(p.getZ(i) * 45 + 1) * 0.003);
  g.computeVertexNormals();
  return g;
}
const noriGeo = sheetGeo();

function berries() {
  const g = new THREE.Group();
  for (const [x, z] of [[-0.07, 0.03], [0.07, 0.03], [0, -0.07]]) {
    const b = new THREE.Mesh(berryGeo, berryMat);
    b.position.set(x, 0.11, z);
    g.add(b);
  }
  const leaf = new THREE.Mesh(leafGeo, leafMat);
  leaf.position.set(0, 0.22, 0);
  leaf.rotation.y = 0.6;
  g.add(leaf);
  return g;
}

function seaweed() {
  const g = new THREE.Group();
  // a neat little stack, each sheet a touch askew
  for (let i = 0; i < 3; i++) {
    const s = new THREE.Mesh(noriGeo, noriMat);
    s.position.set(i * 0.012, 0.03 + i * 0.018, -i * 0.01);
    s.rotation.y = i * 0.12 - 0.12;
    g.add(s);
  }
  return g;
}

interface Shown {
  root: THREE.Group;
  snack: Snack;
  age: number;
}

export class Snacks {
  private shown = new Map<number, Shown>();

  constructor(private scene: THREE.Scene) {}

  // what's on the floor now; returns the ones gone since last time
  set(snacks: Snack[]): Snack[] {
    const now = new Set(snacks.map((s) => s.id));
    const gone: Snack[] = [];
    for (const [id, s] of this.shown) {
      if (now.has(id)) continue;
      this.scene.remove(s.root);
      this.shown.delete(id);
      gone.push(s.snack);
    }
    for (const snack of snacks) {
      if (this.shown.has(snack.id)) continue;
      const root = new THREE.Group();
      const food = snack.kind === 'seaweed' ? seaweed() : berries();
      food.scale.setScalar(SIZE);
      root.add(new THREE.Mesh(glowGeo, glowMat), food);
      root.position.set(snack.x, 0.02, snack.y);
      root.rotation.y = snack.id * 2.4;
      this.scene.add(root);
      this.shown.set(snack.id, { root, snack, age: 0 });
    }
    return gone;
  }

  render(dt: number, time: number) {
    for (const s of this.shown.values()) {
      s.age += dt;
      const k = Math.min(1, s.age / POP);
      // a little overshoot as it pops up
      s.root.scale.setScalar(k < 1 ? Math.sin(k * Math.PI * 0.75) / Math.sin(Math.PI * 0.75) : 1);
      const food = s.root.children[1];
      food.position.y = 0.06 + Math.sin(time * 3 + s.snack.id) * 0.05;
      food.rotation.y += dt * 0.6;
    }
  }

  clear() {
    for (const s of this.shown.values()) this.scene.remove(s.root);
    this.shown.clear();
  }
}
