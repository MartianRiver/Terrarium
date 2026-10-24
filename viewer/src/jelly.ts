// A colony's store, drawn as a heap of jelly drops on its nest around the
// hole: one drop per food unloaded, spiralling out and stacking up as it grows.

import * as THREE from 'three';
import { NEST_TOP } from './garden';
import type { NestInfo } from './world';

// past this many drops the heap stops growing and the drops swell instead
const MOST = 120;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export const dropGeo = new THREE.SphereGeometry(0.09, 14, 10).scale(1, 0.75, 1);
export const jellyMat = new THREE.MeshPhysicalMaterial({
  color: 0xffb03a, emissive: 0xff8a1f, emissiveIntensity: 0.25, roughness: 0.15, clearcoat: 1, transparent: true, opacity: 0.88,
});

export class JellyPile {
  readonly root: THREE.InstancedMesh;
  private shown = -1;
  private m = new THREE.Matrix4();
  private p = new THREE.Vector3();
  private q = new THREE.Quaternion();
  private s = new THREE.Vector3();

  constructor(private nest: NestInfo) {
    this.root = new THREE.InstancedMesh(dropGeo, jellyMat, MOST);
    this.root.castShadow = true;
    this.root.count = 0;
  }

  update(jelly: number) {
    if (jelly === this.shown) return;
    this.shown = jelly;
    const n = Math.min(jelly, MOST);
    const swell = jelly > MOST ? Math.min(1.6, Math.sqrt(jelly / MOST)) : 1;
    const { x, y, radius } = this.nest;
    const inner = radius * 0.3;
    for (let i = 0; i < n; i++) {
      // a spiral out from the hole's edge, each ring of 30 a layer higher
      const d = inner + 0.08 + ((i % 30) / 30) * radius * 0.5;
      const a = i * GOLDEN;
      this.p.set(x + Math.cos(a) * d, NEST_TOP + 0.05 + Math.floor(i / 30) * 0.09, y + Math.sin(a) * d);
      this.q.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, a);
      this.s.setScalar(swell);
      this.root.setMatrixAt(i, this.m.compose(this.p, this.q, this.s));
    }
    this.root.count = n;
    this.root.instanceMatrix.needsUpdate = true;
  }

  dispose() {
    this.root.dispose();
  }
}
