import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { dropGeo, jellyMat } from './jelly';
import type { BlockState, FoodKind, FoodState } from './world';

export const berryGeo = new THREE.SphereGeometry(0.11, 20, 14);
export const leafGeo = new THREE.SphereGeometry(0.1, 8, 6).scale(1, 0.25, 1.8);
export const berryMat = new THREE.MeshPhysicalMaterial({ color: 0xff5a6e, roughness: 0.5, sheen: 0.5 });
export const leafMat = new THREE.MeshStandardMaterial({ color: 0x5fae4e, roughness: 0.7 });
// what a hidden berry is drawn in: there for us, not for them
const ghostMat = new THREE.MeshStandardMaterial({ color: 0xffa3b3, transparent: true, opacity: 0.5, depthWrite: false });
// and a dashed ring round it on the ground that turns slowly, so it can be found on a phone screen
function dashedRing(): THREE.Mesh {
  const parts: THREE.BufferGeometry[] = [];
  const dashes = 10;
  for (let i = 0; i < dashes; i++) {
    parts.push(new THREE.RingGeometry(0.42, 0.54, 4, 1, (i / dashes) * Math.PI * 2, (Math.PI * 2) / dashes * 0.55));
  }
  const geo = mergeGeometries(parts).rotateX(-Math.PI / 2);
  for (const g of parts) g.dispose();
  const mat = new THREE.MeshBasicMaterial({ color: 0xffa3b3, transparent: true, opacity: 0.8, depthWrite: false });
  const ring = new THREE.Mesh(geo, mat);
  ring.position.y = 0.03;
  return ring;
}
// a wooden toy block, like the rest of the garden
const blockMat = new THREE.MeshPhysicalMaterial({ color: 0xe2bf8f, roughness: 0.6, sheen: 0.4, sheenColor: new THREE.Color(0xfff3dd) });

const SPAWN_TIME = 0.45;
const DESPAWN_TIME = 0.25;

// overshooting pop-in
function easeOutBack(t: number) {
  const c = 1.9;
  return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2);
}

function buildFood(kind: FoodKind): THREE.Group {
  const g = new THREE.Group();
  if (kind === 'jelly') {
    const drop = new THREE.Mesh(dropGeo, jellyMat);
    drop.scale.setScalar(1.6);
    drop.position.y = 0.11;
    drop.castShadow = true;
    g.add(drop);
    return g;
  }
  const offsets: [number, number][] = [[0, 0], [0.13, 0.07], [0.04, -0.13]];
  for (const [x, z] of offsets) {
    const b = new THREE.Mesh(berryGeo, berryMat);
    b.position.set(x, 0.1, z);
    b.castShadow = true;
    g.add(b);
  }
  const leaf = new THREE.Mesh(leafGeo, leafMat);
  leaf.position.set(0.05, 0.22, 0);
  leaf.rotation.set(0.3, 0.6, 0.2);
  g.add(leaf);
  return g;
}

export class FoodView {
  readonly root: THREE.Group;
  private age = 0;
  private dying = -1;
  private seed = Math.random() * 10;
  private hidden = false;
  private looks = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
  private ring: THREE.Mesh | null = null;

  constructor(readonly state: FoodState) {
    this.root = buildFood(state.kind);
    this.root.position.set(state.x, 0, state.y);
    this.root.rotation.y = this.seed;
    this.root.scale.setScalar(0.001);
    this.sync(state);
  }

  despawn() {
    if (this.dying < 0) this.dying = 0;
  }

  // peekaboo moves its berry where someone can see it, and hides it a second later
  sync(s: FoodState) {
    this.root.position.set(s.x, 0, s.y);
    if (s.hidden === this.hidden) return;
    this.hidden = s.hidden;
    this.root.traverse((o) => {
      if (!(o instanceof THREE.Mesh) || o === this.ring) return;
      if (!this.looks.has(o)) this.looks.set(o, o.material);
      o.material = s.hidden ? ghostMat : this.looks.get(o)!;
      o.castShadow = !s.hidden;
    });
    if (s.hidden && !this.ring) {
      this.ring = dashedRing();
      this.root.add(this.ring);
    }
    if (this.ring) this.ring.visible = s.hidden;
  }

  // false once the view has finished despawning and can be removed
  update(dt: number): boolean {
    this.age += dt;
    let scale = this.age < SPAWN_TIME ? easeOutBack(this.age / SPAWN_TIME) : 1;
    if (this.dying >= 0) {
      this.dying += dt;
      scale *= Math.max(0, 1 - this.dying / DESPAWN_TIME);
    }
    this.root.scale.setScalar(Math.max(0.001, scale));
    if (this.ring?.visible) {
      this.ring.rotation.y += dt * 0.8;
      (this.ring.material as THREE.MeshBasicMaterial).opacity = 0.55 + 0.25 * Math.sin(this.age * 4);
    }
    if (this.dying >= DESPAWN_TIME) this.dispose();
    return this.dying < DESPAWN_TIME;
  }

  private dispose() {
    if (!this.ring) return;
    this.ring.geometry.dispose();
    (this.ring.material as THREE.Material).dispose();
    this.ring = null;
  }
}

// how high a carried block rides: just above a Terrikin's bulb
const CARRY_HEIGHT = 1.05;

export class BlockView {
  readonly root: THREE.Mesh;
  private height = 0.8;

  constructor(state: BlockState) {
    this.root = new THREE.Mesh(new RoundedBoxGeometry(state.w, this.height, state.h, 4, 0.12), blockMat);
    this.root.castShadow = true;
    this.root.receiveShadow = true;
    this.update(state);
  }

  update(s: BlockState) {
    // a carried one rides on top of its carrier's head
    this.root.position.set(s.x, this.height / 2 + (s.carried ? CARRY_HEIGHT : 0), s.y);
    this.root.rotation.y = -s.angle;
  }

  dispose() {
    this.root.geometry.dispose();
  }
}
