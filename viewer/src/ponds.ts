// Ponds ([water], a replay's info.ponds): a shallow disc of water on the lawn, pale at the edge, on a damp bank with a
// few pebbles. Flat ground like a nest, so nims walk straight in: it sits a hair above the lawn and nothing else.

import * as THREE from 'three';
import { GARDEN } from './palette';
import type { PondInfo } from './world';

// heights above the lawn (0.005): bank, water, shallows
const BANK = 0.007, SURFACE = 0.011, SHALLOWS = 0.012;

const flat = (geo: THREE.BufferGeometry) => geo.rotateX(-Math.PI / 2);

export function addPonds(scene: THREE.Object3D, ponds: PondInfo[]) {
  const stones = new THREE.IcosahedronGeometry(1, 1);
  const stoneMat = new THREE.MeshStandardMaterial({ roughness: 0.85 });
  ponds.forEach((p, k) => {
    const group = new THREE.Group();
    group.position.set(p.x, 0, p.y);
    const bank = new THREE.Mesh(flat(new THREE.CircleGeometry(p.radius * 1.12, 64)), new THREE.MeshStandardMaterial({ color: GARDEN.bank, roughness: 1 }));
    bank.position.y = BANK;
    const water = new THREE.Mesh(
      flat(new THREE.CircleGeometry(p.radius, 64)),
      new THREE.MeshStandardMaterial({ color: GARDEN.water, roughness: 0.15, transparent: true, opacity: 0.9 }),
    );
    water.position.y = SURFACE;
    const shallows = new THREE.Mesh(
      flat(new THREE.RingGeometry(p.radius * 0.8, p.radius, 64)),
      new THREE.MeshStandardMaterial({ color: GARDEN.shallows, roughness: 0.2, transparent: true, opacity: 0.55 }),
    );
    shallows.position.y = SHALLOWS;
    bank.receiveShadow = water.receiveShadow = true;
    // pebbles round the bank, not touching the water
    const n = Math.round(p.radius * 12);
    const pebbles = new THREE.InstancedMesh(stones, stoneMat, n);
    const d = new THREE.Object3D();
    const c = new THREE.Color();
    for (let i = 0; i < n; i++) {
      // a plain hash of the pond and the stone, so every viewer draws the same ring
      const r1 = Math.abs(Math.sin((i + 1) * 12.9898 + k * 78.233)), r2 = Math.abs(Math.sin((i + 1) * 4.1414 + k * 37.719));
      const a = ((i + r1 * 0.6) / n) * Math.PI * 2;
      const s = 0.04 + r2 * 0.035;
      d.position.set(Math.cos(a) * p.radius * 1.13, s * 0.3, Math.sin(a) * p.radius * 1.13);
      d.scale.set(s, s * 0.6, s);
      d.updateMatrix();
      pebbles.setMatrixAt(i, d.matrix);
      pebbles.setColorAt(i, c.set(GARDEN.pebbles[i % GARDEN.pebbles.length]));
    }
    pebbles.castShadow = pebbles.receiveShadow = true;
    group.add(bank, water, shallows, pebbles);
    scene.add(group);
  });
}
