// The blob's animation has to survive slow frames (main.ts hands it up to 0.1 s at a
// time), and it has to stay inside the sim's body, or touching blobs look merged.

import * as THREE from 'three';
import { expect, test } from 'vitest';
import { BlobView } from '../src/blob';

const RADIUS = 0.45; // sim/configs/world.toml [creature] radius
const walking = { id: 1, colony: 0, x: 0, y: 0, heading: 0, speed: 2.4, size: 1, energy: 0.9, signal: -1, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1, dung: 0, z: 0 };

// furthest any vertex is drawn from the blob's centre, across the ground
function reach(blob: BlobView) {
  blob.root.updateMatrixWorld(true);
  const v = new THREE.Vector3();
  let far = 0;
  blob.root.traverse((o) => {
    if (!(o instanceof THREE.Mesh)) return;
    const p = o.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i).applyMatrix4(o.matrixWorld);
      far = Math.max(far, Math.hypot(v.x, v.z));
    }
  });
  return far;
}

test('a blob stays in shape at 10 fps', () => {
  const blob = new BlobView(0);
  for (let i = 0; i < 600; i++) blob.update({ ...walking, heading: i * 0.05 }, 2.4, 0.1, i * 0.1);
  const body = blob.root.children.at(-1)!.scale;
  expect(body.y).toBeGreaterThan(0.7);
  expect(body.y).toBeLessThan(1.3);
  expect(body.x).toBeGreaterThan(0.7);
  expect(body.x).toBeLessThan(1.3);
});

test('a blob is drawn inside its body, walking, turning, full or starving, carrying or not', () => {
  for (const [energy, carrying] of [[1, 0], [0.6, 3], [0.02, 0]]) {
    const blob = new BlobView(0);
    let far = 0;
    for (let i = 0; i < 300; i++) {
      blob.update({ ...walking, energy, carrying, heading: Math.sin(i * 0.1) * 2 }, 2.4, 1 / 30, i / 30);
      far = Math.max(far, reach(blob));
    }
    expect(far, `energy ${energy}`).toBeLessThanOrEqual(RADIUS + 0.02);
  }
});
