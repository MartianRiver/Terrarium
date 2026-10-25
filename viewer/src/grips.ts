// A Terrikin holding a block (grab, from 0.3's vault) reaches out to it: a short
// clay arm in its colony's colour, from its body to the nearest point on the
// block. The sim holds it by a joint at the point it touched; nearest is close
// enough to show who's pulling what.

import * as THREE from 'three';
import { COLONY_COLOURS } from './palette';

const HEIGHT = 0.22;
const geo = new THREE.CylinderGeometry(0.055, 0.075, 1, 10, 1).rotateX(Math.PI / 2);
const materials = COLONY_COLOURS.map((c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.6 }));

export interface Holder { x: number; y: number; colony: number }
export interface Box { x: number; y: number; angle: number; w: number; h: number }

export function nearestPoint(p: { x: number; y: number }, b: Box) {
  const cos = Math.cos(b.angle), sin = Math.sin(b.angle);
  const dx = p.x - b.x, dy = p.y - b.y;
  const lx = Math.max(-b.w / 2, Math.min(b.w / 2, dx * cos + dy * sin));
  const ly = Math.max(-b.h / 2, Math.min(b.h / 2, -dx * sin + dy * cos));
  return { x: b.x + lx * cos - ly * sin, y: b.y + lx * sin + ly * cos };
}

export class Grips {
  private arms: THREE.Mesh[] = [];

  constructor(private scene: THREE.Scene) {}

  update(holders: Holder[], blocks: Box[]) {
    while (this.arms.length < holders.length) {
      const arm = new THREE.Mesh(geo, materials[0]);
      arm.castShadow = true;
      this.scene.add(arm);
      this.arms.push(arm);
    }
    this.arms.forEach((arm, i) => {
      const h = holders[i];
      arm.visible = h !== undefined && blocks.length > 0;
      if (!arm.visible) return;
      let to = { x: h.x, y: h.y };
      let best = Infinity;
      for (const b of blocks) {
        const q = nearestPoint(h, b);
        const d = (q.x - h.x) ** 2 + (q.y - h.y) ** 2;
        if (d < best) [to, best] = [q, d];
      }
      // sim (x, y) is three (x, z)
      arm.material = materials[h.colony % materials.length];
      arm.position.set((h.x + to.x) / 2, HEIGHT, (h.y + to.y) / 2);
      arm.scale.set(1, 1, Math.max(Math.sqrt(best), 0.05));
      arm.lookAt(to.x, HEIGHT, to.y);
    });
  }

  clear() {
    for (const arm of this.arms) this.scene.remove(arm);
    this.arms = [];
  }
}
