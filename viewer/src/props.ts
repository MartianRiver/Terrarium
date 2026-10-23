import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import type { BlockState, FoodKind, FoodState } from './world';

const berryGeo = new THREE.SphereGeometry(0.11, 20, 14);
const leafGeo = new THREE.SphereGeometry(0.1, 8, 6).scale(1, 0.25, 1.8);
const berryMat = new THREE.MeshPhysicalMaterial({ color: 0xff5a6e, roughness: 0.5, sheen: 0.5 });
const leafMat = new THREE.MeshStandardMaterial({ color: 0x5fae4e, roughness: 0.7 });
const richGeo = new THREE.IcosahedronGeometry(0.32, 0);
const richMat = new THREE.MeshStandardMaterial({
  color: 0xffd166, emissive: 0xffb12b, emissiveIntensity: 1.0, roughness: 0.3, flatShading: true,
});
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
  if (kind === 'rich') {
    const gem = new THREE.Mesh(richGeo, richMat);
    gem.position.y = 0.55;
    gem.castShadow = true;
    g.add(gem);
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

  constructor(readonly state: FoodState) {
    this.root = buildFood(state.kind);
    this.root.position.set(state.x, 0, state.y);
    this.root.rotation.y = this.seed;
    this.root.scale.setScalar(0.001);
  }

  despawn() {
    if (this.dying < 0) this.dying = 0;
  }

  // false once the view has finished despawning and can be removed
  update(dt: number, time: number): boolean {
    this.age += dt;
    let scale = this.age < SPAWN_TIME ? easeOutBack(this.age / SPAWN_TIME) : 1;
    if (this.dying >= 0) {
      this.dying += dt;
      scale *= Math.max(0, 1 - this.dying / DESPAWN_TIME);
    }
    this.root.scale.setScalar(Math.max(0.001, scale));
    if (this.state.kind === 'rich') {
      const gem = this.root.children[0];
      gem.rotation.y = time * 0.8 + this.seed;
      gem.position.y = 0.55 + Math.sin(time * 1.6 + this.seed) * 0.08;
    }
    return this.dying < DESPAWN_TIME;
  }
}

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
    this.root.position.set(s.x, this.height / 2, s.y);
    this.root.rotation.y = -s.angle;
  }

  dispose() {
    this.root.geometry.dispose();
  }
}
