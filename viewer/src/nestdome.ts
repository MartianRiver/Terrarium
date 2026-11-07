// A low woven dome over each nest in its colony's colour: legs that rise from the
// stone ring to a crown, and a frosted cap above the Terrikins' heads, so the
// jelly and the huddle inside stay in view. Only a look: the sim's nest is still a
// flat pad anyone walks across, so the cap leaves the bottom open to walk in under.
// It fades as the camera comes close, so a close-up at the nest still reads.

import * as THREE from 'three';
import { COLONY_COLOURS } from './palette';
import type { NestInfo } from './world';

// the dome's height as a share of its radius (it stands on the stone ring)
const RISE = 0.62;
const LEGS = 8;
// the legs stop at a crown ring this far (radians) short of the top, so they don't bunch up there
const CROWN = 0.4;
// the cap covers this much of the dome down from its top (radians of the full quarter turn)
const CAP = 1.0;
// camera distance (m) where the dome starts to fade, and where it's fully there
const NEAR = 9;
const FAR = 17;
// how much of it is left at its faintest
const FAINTEST = 0.2;

export function addNestDome(scene: THREE.Object3D, nest: NestInfo) {
  const tint = new THREE.Color(COLONY_COLOURS[nest.colony % COLONY_COLOURS.length]);
  const r = nest.radius * 1.15;
  const group = new THREE.Group();
  group.position.set(nest.x, 0, nest.y);
  group.scale.set(1, RISE, 1);

  const weave = new THREE.MeshStandardMaterial({ color: tint, roughness: 0.75, transparent: true });
  // each leg is a quarter circle from the ground to the crown; the group's squash makes it the dome's curve
  const leg = new THREE.TorusGeometry(r, 0.045, 6, 24, Math.PI / 2 - CROWN);
  for (let i = 0; i < LEGS; i++) {
    const mesh = new THREE.Mesh(leg, weave);
    mesh.rotation.y = ((i + 0.5) / LEGS) * Math.PI * 2;
    mesh.castShadow = true;
    group.add(mesh);
  }
  for (const lat of [0.6, Math.PI / 2 - CROWN]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r * Math.cos(lat), 0.04, 6, 60).rotateX(Math.PI / 2), weave);
    ring.position.y = r * Math.sin(lat);
    group.add(ring);
  }

  // front faces only, like the big dome, so a camera inside sees out
  const frost = new THREE.MeshStandardMaterial({
    color: tint.clone().lerp(new THREE.Color(0xffffff), 0.55), emissive: tint, emissiveIntensity: 0.08,
    roughness: 0.3, transparent: true, depthWrite: false,
  });
  const cap = new THREE.Mesh(new THREE.SphereGeometry(r, 40, 12, 0, Math.PI * 2, 0, CAP), frost);
  // after the jelly heap, which sits at the same spot and is see-through too
  cap.renderOrder = 1;
  group.add(cap);
  scene.add(group);

  const centre = new THREE.Vector3(nest.x, r * RISE * 0.5, nest.y);
  let shown = -1;
  return (camera: THREE.Camera) => {
    const k = THREE.MathUtils.smoothstep(camera.position.distanceTo(centre), NEAR, FAR);
    const seen = FAINTEST + (1 - FAINTEST) * k;
    if (Math.abs(seen - shown) < 0.01) return;
    shown = seen;
    weave.opacity = seen;
    weave.depthWrite = seen > 0.99;
    frost.opacity = 0.2 * seen;
  };
}
