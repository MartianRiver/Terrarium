// The followed Terrikin's rays drawn in the world while the brain window is open: a ribbon on the ground out along
// each ray to whatever it hit, in that thing's colour, wider and stronger the more the brain is listening to it.

import * as THREE from 'three';
import type { MindHeader, Thought } from './mindtrack';
import { KINDS } from './mindtext';

const HEIGHT = 0.04;
// ribbon half-widths (m) and opacity for a ray nobody's listening to and the one listened to most
const THIN = 0.012;
const WIDE = 0.07;
const FAINT = 0.15;

export interface Pose {
  x: number;
  y: number;
  heading: number;
}

export class SightFan {
  private mesh: THREE.Mesh;
  private positions: Float32Array;
  private colours: Float32Array;
  private colour = new THREE.Color();

  constructor(private scene: THREE.Scene, rays: number) {
    this.positions = new Float32Array(rays * 12);
    this.colours = new Float32Array(rays * 16);
    const index: number[] = [];
    for (let i = 0; i < rays; i++) index.push(i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 2, i * 4 + 1, i * 4 + 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(this.colours, 4));
    geo.setIndex(index);
    const mat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide });
    this.mesh = new THREE.Mesh(geo, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 2;
    scene.add(this.mesh);
  }

  update(at: Pose | null, t: Thought | null, head: MindHeader) {
    this.mesh.visible = !!(at && t);
    if (!at || !t) return;
    const { count, fov, range } = head.rays;
    const last = t.attention.at(-1)!;
    const heard = t.kinds.map((_, i) => last.reduce((s, h) => s + h[i + 1], 0) / last.length);
    const most = Math.max(...heard, 1e-6);
    for (let i = 0; i < count; i++) {
      const share = heard[i] / most;
      const a = at.heading + (count > 1 ? -fov / 2 + (fov * i) / (count - 1) : 0);
      const [dx, dy] = [Math.cos(a), Math.sin(a)];
      const w = THIN + (WIDE - THIN) * share;
      const d = t.dist[i] * range;
      // two corners at the Terrikin, two at the end of the ray
      const ends = [[0, -w], [0, w], [d, -w], [d, w]];
      ends.forEach(([along, side], k) => {
        this.positions.set([at.x + dx * along - dy * side, HEIGHT, at.y + dy * along + dx * side], (i * 4 + k) * 3);
      });
      const kind = head.brain.schema.kinds[t.kinds[i]];
      this.colour.set(KINDS[kind]?.colour ?? '#999999');
      const alpha = FAINT + (1 - FAINT) * share;
      for (let k = 0; k < 4; k++) this.colours.set([this.colour.r, this.colour.g, this.colour.b, alpha], (i * 4 + k) * 4);
    }
    this.mesh.geometry.attributes.position.needsUpdate = true;
    this.mesh.geometry.attributes.color.needsUpdate = true;
  }

  hide() {
    this.mesh.visible = false;
  }

  dispose() {
    this.scene.remove(this.mesh);
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
