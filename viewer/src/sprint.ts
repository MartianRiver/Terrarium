// Puffs of dust kicked up behind a sprinting Terrikin, rainbow-flecked while it's
// on nectar. Purely cosmetic and timed on the wall clock, like the waddle.

import * as THREE from 'three';
import { shimmer } from './palette';

const EVERY = 0.05; // seconds between puffs while sprinting
const LIFE = 0.55;
const DUST = new THREE.Color(0xe2cfae);
const puffGeo = new THREE.SphereGeometry(0.09, 8, 6);

interface Puff { mesh: THREE.Mesh; mat: THREE.MeshStandardMaterial; age: number; vx: number; vz: number }

export class Dust {
  private puffs: Puff[] = [];
  private since = new Map<number, number>();
  private tint = new THREE.Color();

  constructor(private scene: THREE.Scene) {}

  // behind creature `id` at (x, y) facing `heading`, for this frame's dt
  kick(id: number, x: number, y: number, heading: number, dt: number, time: number, nectar: boolean) {
    const due = (this.since.get(id) ?? EVERY) + dt;
    if (due < EVERY) {
      this.since.set(id, due);
      return;
    }
    this.since.set(id, 0);
    const side = (Math.random() - 0.5) * 0.3;
    const back = [-Math.cos(heading), -Math.sin(heading)];
    const mat = new THREE.MeshStandardMaterial({ roughness: 1, transparent: true, opacity: 0.7, depthWrite: false });
    mat.color.copy(nectar ? shimmer(time, Math.random() * 6, this.tint).lerp(DUST, 0.35) : DUST);
    const mesh = new THREE.Mesh(puffGeo, mat);
    mesh.position.set(x + back[0] * 0.35 - back[1] * side, 0.06, y + back[1] * 0.35 + back[0] * side);
    this.scene.add(mesh);
    this.puffs.push({ mesh, mat, age: 0, vx: back[0] * 0.6, vz: back[1] * 0.6 });
  }

  render(dt: number) {
    this.puffs = this.puffs.filter((p) => {
      p.age += dt;
      const t = p.age / LIFE;
      p.mesh.position.x += p.vx * dt;
      p.mesh.position.z += p.vz * dt;
      p.mesh.position.y += dt * 0.25;
      p.mesh.scale.setScalar(0.6 + t * 1.6);
      p.mat.opacity = 0.7 * (1 - t);
      if (t < 1) return true;
      this.scene.remove(p.mesh);
      p.mat.dispose();
      return false;
    });
  }

  clear() {
    for (const p of this.puffs) {
      this.scene.remove(p.mesh);
      p.mat.dispose();
    }
    this.puffs = [];
    this.since.clear();
  }
}
