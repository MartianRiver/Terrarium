// Capture the flag's flags, from a frame's `flags`: a little pennant in its colony's tint, planted on its nest, lying
// on the grass where it was put down, or held up on its carrier's back, fluttering out behind.

import * as THREE from 'three';
import { COLONY_COLOURS } from './palette';
import type { Pose } from './sightfan';
import type { FlagState } from './world';

const POLE = 1.5;
const CARRIED = 0.3; // how high off the ground a carrier holds it
const BEHIND = 0.22; // and how far back from its middle
const LYING = 1.35; // tipped over this far (radians) when it's down
const BREEZE = 0.6; // the way a planted flag's cloth points

const poleGeo = new THREE.CylinderGeometry(0.025, 0.03, POLE, 6).translate(0, POLE / 2, 0);
const knobGeo = new THREE.SphereGeometry(0.06, 10, 8).translate(0, POLE, 0);
// a pennant along +x from the top of the pole
const clothGeo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(
  [0, POLE - 0.03, 0, 0, POLE - 0.48, 0, 0.7, POLE - 0.25, 0], 3));
clothGeo.computeVertexNormals();
const poleMat = new THREE.MeshStandardMaterial({ color: 0xf2e6d0, roughness: 0.6 });

export class Flags {
  private flags: { root: THREE.Group; cloth: THREE.Mesh }[] = [];

  constructor(private scene: THREE.Scene) {}

  render(states: FlagState[], poses: Map<number, Pose>, time: number) {
    for (const f of this.flags) f.root.visible = false;
    for (const s of states) {
      while (this.flags.length <= s.colony) this.flags.push(this.make(this.flags.length));
      const { root, cloth } = this.flags[s.colony];
      root.visible = true;
      const carrier = s.carrier >= 0 ? poses.get(s.carrier) : undefined;
      if (carrier) {
        const back = carrier.heading + Math.PI;
        root.position.set(carrier.x + Math.cos(back) * BEHIND, CARRIED, carrier.y + Math.sin(back) * BEHIND);
        root.rotation.set(0, -back, 0);
      } else {
        root.position.set(s.x, 0, s.y);
        root.rotation.set(0, -BREEZE, s.down ? LYING : 0);
      }
      // carried, it streams out behind; planted or down, it stirs
      const flutter = carrier ? 0.35 : s.down ? 0.05 : 0.15;
      cloth.rotation.y = Math.sin(time * (carrier ? 9 : 3) + s.colony * 2) * flutter;
    }
  }

  clear() {
    for (const f of this.flags) f.root.visible = false;
  }

  private make(colony: number) {
    const root = new THREE.Group();
    const tint = COLONY_COLOURS[colony % COLONY_COLOURS.length];
    root.add(new THREE.Mesh(poleGeo, poleMat), new THREE.Mesh(knobGeo, poleMat));
    const cloth = new THREE.Mesh(clothGeo, new THREE.MeshStandardMaterial({ color: tint, roughness: 0.55, side: THREE.DoubleSide, emissive: tint, emissiveIntensity: 0.15 }));
    root.add(cloth);
    root.traverse((o) => (o.castShadow = true));
    root.visible = false;
    this.scene.add(root);
    return { root, cloth };
  }
}
