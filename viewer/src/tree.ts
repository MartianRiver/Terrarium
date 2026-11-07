import * as THREE from 'three';
import { GARDEN } from './palette';
import type { BlockState, FoodState } from './world';

// where a standing Terrikin's head gets to: an apple's `z` is how far above this it hangs
export const REACH = 0.78;
const TRUNK = 2.2;
// where the branches leave the trunk, and how far above an apple's top its branch ends
const FORK = 1.85;
const STALK = 0.08;

const bark = new THREE.MeshStandardMaterial({ color: GARDEN.bark, roughness: 0.9 });
const leaves = new THREE.MeshStandardMaterial({ color: 0x5aa84a, roughness: 0.8 });
const crownGeo = new THREE.IcosahedronGeometry(0.5, 2);
const trunkGeo = new THREE.CylinderGeometry(0.17, 0.26, TRUNK, 10).translate(0, TRUNK / 2, 0);
const branchGeo = new THREE.CylinderGeometry(0.025, 0.04, 1, 6).translate(0, 0.5, 0);
const tuftGeo = new THREE.IcosahedronGeometry(0.13, 1);
const up = new THREE.Vector3(0, 1, 0);

// the trunk and crown, in these materials (the ghost tree has its own); the geometry is shared, never disposed
export function treeModel(trunkMat: THREE.Material, leafMat: THREE.Material, shadows = true): THREE.Group {
  const root = new THREE.Group();
  const trunk = new THREE.Mesh(trunkGeo, trunkMat);
  trunk.castShadow = shadows;
  root.add(trunk);
  const crown: [number, number, number, number][] = [[0, 2.45, 0, 1.15], [0.35, 2.25, 0.2, 0.8], [-0.3, 2.3, -0.25, 0.85], [0.05, 2.25, -0.4, 0.75]];
  for (const [x, y, z, s] of crown) {
    const ball = new THREE.Mesh(crownGeo, leafMat);
    ball.position.set(x, y, z);
    ball.scale.setScalar(s);
    ball.castShadow = shadows;
    root.add(ball);
  }
  return root;
}

// The apple tree's trunk ([tree]): drawn as an apple tree in place of a block, its crown kept small and high so the
// camera still sees the baby underneath, and a branch out to every apple hanging from it.
export class TreeView {
  readonly root = treeModel(bark, leaves);
  private branches = new Map<number, THREE.Group>();

  constructor(state: BlockState) {
    this.update(state);
  }

  update(s: BlockState) {
    this.root.position.set(s.x, 0, s.y);
  }

  // a branch from the trunk to each apple, gone with it
  apples(food: FoodState[]) {
    const seen = new Set<number>();
    for (const f of food) {
      if (f.kind !== 'apple') continue;
      seen.add(f.id);
      if (this.branches.has(f.id)) continue;
      const g = new THREE.Group();
      const from = new THREE.Vector3(this.root.position.x, FORK, this.root.position.z);
      const to = new THREE.Vector3(f.x, REACH + f.z + 0.26 + STALK, f.y);
      const branch = new THREE.Mesh(branchGeo, bark);
      branch.position.copy(from);
      branch.scale.set(1, from.distanceTo(to), 1);
      branch.quaternion.setFromUnitVectors(up, to.clone().sub(from).normalize());
      branch.castShadow = true;
      const tuft = new THREE.Mesh(tuftGeo, leaves);
      tuft.position.copy(to);
      tuft.castShadow = true;
      g.add(branch, tuft);
      this.branches.set(f.id, g);
      this.root.parent?.add(g);
    }
    for (const [id, g] of this.branches) {
      if (seen.has(id)) continue;
      g.removeFromParent();
      this.branches.delete(id);
    }
  }

  dispose() {
    for (const g of this.branches.values()) g.removeFromParent();
    this.branches.clear();
  }
}
