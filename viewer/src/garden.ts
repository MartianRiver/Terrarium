// Everything that depends on the world's layout: the sun's shadow box, the lawn,
// the hedge on the walls, nests and their domes (nestdome.ts), the glass dome over
// them on a red plain, and seeded decoration. Decoration is purely visual and stays outside the hedge (or
// flat inside it), so nothing looks like an obstacle the sim ignores.

import * as THREE from 'three';
import { addNestDome } from './nestdome';
import { COLONY_COLOURS, GARDEN } from './palette';
import type { NestInfo, WorldInfo } from './world';

// how far rocks reach past the dome, metres
const REACH = 45;
// the glass wall's height; the dome rises from its top
export const WALL = 1.1;

function seeded(seed: number) {
  return () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

const ball = new THREE.SphereGeometry(1, 20, 14);
const pick = <T>(rng: () => number, list: readonly T[]) => list[Math.floor(rng() * list.length)];

export function buildGarden(info: WorldInfo) {
  const group = new THREE.Group();
  const rng = seeded(42);
  addSun(group, info);
  addGround(group, info);
  addHedge(group, info, rng);
  for (const nest of info.nests) addNest(group, nest);
  const domes = info.nests.map((nest) => addNestDome(group, nest));
  const sway = addGrass(group, info, rng);
  addPebbles(group, info, rng);
  addTrees(group, info, rng);
  addFlowers(group, info, rng);
  const frame = addDome(group, info);
  addRocks(group, info, rng);
  addMesas(group, rng);
  return {
    group,
    tick(time: number, camera: THREE.Camera) {
      sway.value = time;
      for (const fade of domes) fade(camera);
      frame(camera);
    },
  };
}

// the dome covers the arena's corners with a planted bed to spare
export const domeRadius = (info: WorldInfo) => Math.hypot(info.width, info.height) / 2 + 2.5;

// a random spot in the bed: under the dome, outside the hedge (plus margin)
function inBed(rng: () => number, info: WorldInfo, margin: number) {
  const r = domeRadius(info) - 0.5;
  const hx = info.width / 2 + margin, hz = info.height / 2 + margin;
  for (;;) {
    const x = (rng() * 2 - 1) * r, z = (rng() * 2 - 1) * r;
    if (Math.hypot(x, z) < r && (Math.abs(x) > hx || Math.abs(z) > hz)) return [x, z];
  }
}

// how many to scatter in the bed for a given number per square metre
function count(info: WorldInfo, perSquareMetre: number) {
  const area = Math.PI * domeRadius(info) ** 2 - info.width * info.height;
  return Math.round(area * perSquareMetre);
}

function instanced(geo: THREE.BufferGeometry, mat: THREE.Material, n: number, place: (d: THREE.Object3D, i: number) => number | void) {
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  const d = new THREE.Object3D();
  const c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    d.position.set(0, 0, 0);
    d.rotation.set(0, 0, 0);
    d.scale.setScalar(1);
    const colour = place(d, i);
    d.updateMatrix();
    mesh.setMatrixAt(i, d.matrix);
    if (colour !== undefined) mesh.setColorAt(i, c.set(colour));
  }
  return mesh;
}

// a seamless tile of flecks on a base colour, optionally with a mown stripe down one half
function flecks(base: string, colours: string[], n: number, maxR: number, seed: number, stripe?: string) {
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const g = canvas.getContext('2d')!;
  g.fillStyle = base;
  g.fillRect(0, 0, size, size);
  if (stripe) {
    g.fillStyle = stripe;
    g.fillRect(0, 0, size / 2, size);
  }
  const rng = seeded(seed);
  for (let i = 0; i < n; i++) {
    const x = rng() * size, y = rng() * size, r = 0.8 + rng() * rng() * maxR;
    g.globalAlpha = 0.2 + rng() * 0.5;
    g.fillStyle = pick(rng, colours);
    // drawn at the wrapped copies too, so the tile has no seams
    for (const dx of [-size, 0, size]) for (const dy of [-size, 0, size]) {
      g.beginPath();
      g.arc(x + dx, y + dy, r, 0, Math.PI * 2);
      g.fill();
    }
  }
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

function addSun(scene: THREE.Object3D, info: WorldInfo) {
  const sun = new THREE.DirectionalLight(GARDEN.sun, 2.7);
  // low from the side, for long soft shadows
  sun.position.set(-13, 12, 9).setLength(40);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const r = Math.max(info.width, info.height) * 0.75;
  Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 1, far: 90 });
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.03;
  sun.shadow.radius = 6;
  scene.add(sun);
}

function addGround(scene: THREE.Object3D, info: WorldInfo) {
  const dust = flecks(GARDEN.regolith, GARDEN.regolithFlecks, 3000, 7, 5);
  dust.repeat.set(50, 50);
  const plain = new THREE.Mesh(new THREE.CircleGeometry(80, 64).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ map: dust, roughness: 0.95 }));
  plain.receiveShadow = true;
  const r = domeRadius(info);
  const grass = flecks(GARDEN.grass, GARDEN.grassFlecks, 2500, 6, 3);
  grass.repeat.set(r / 1.6, r / 1.6);
  const bed = new THREE.Mesh(new THREE.CircleGeometry(r, 96).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ map: grass, roughness: 0.8 }));
  bed.position.y = 0.003;
  bed.receiveShadow = true;
  // mown in stripes a metre wide, so the play area reads clearly
  const inner = flecks(GARDEN.lawn, GARDEN.lawnFlecks, 700, 4, 4, GARDEN.lawnStripe);
  inner.repeat.set(info.width / 2, info.height / 2);
  const lawn = new THREE.Mesh(new THREE.PlaneGeometry(info.width, info.height).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ map: inner, roughness: 0.8 }));
  lawn.position.y = 0.005;
  lawn.receiveShadow = true;
  scene.add(plain, bed, lawn);
}

// round bushes along each wall, kept outside the arena's edge
function addHedge(scene: THREE.Object3D, info: WorldInfo, rng: () => number) {
  const spots: [number, number, number][] = [];
  const edge = 0.44;
  const hx = info.width / 2 + edge, hz = info.height / 2 + edge;
  for (const [length, fixed, along] of [[info.width + edge * 2, hz, true], [info.width + edge * 2, -hz, true], [info.height, hx, false], [info.height, -hx, false]] as const) {
    const n = Math.round(length / 0.55);
    for (let i = 0; i < n; i++) {
      const p = ((i + 0.5) / n) * length - length / 2;
      spots.push(along ? [p, fixed, 0.36 + rng() * 0.08] : [fixed, p, 0.36 + rng() * 0.08]);
    }
  }
  const hedge = instanced(ball, new THREE.MeshStandardMaterial({ color: GARDEN.hedge, roughness: 0.8 }), spots.length, (d, i) => {
    const [x, z, s] = spots[i];
    d.position.set(x, s * 0.8, z);
    d.scale.set(s, s * 0.9, s);
  });
  hedge.castShadow = hedge.receiveShadow = true;
  scene.add(hedge);
}

// a nest is a flat pad of soil: Terrikins walk across it in the sim, so anything taller swallows their feet
export const NEST_TOP = 0.04;

function addNest(scene: THREE.Object3D, nest: NestInfo) {
  const tint = COLONY_COLOURS[nest.colony % COLONY_COLOURS.length];
  const pad = new THREE.Mesh(
    new THREE.CylinderGeometry(nest.radius, nest.radius * 1.04, NEST_TOP, 48),
    new THREE.MeshStandardMaterial({ color: GARDEN.soil, roughness: 1 }),
  );
  pad.position.set(nest.x, NEST_TOP / 2, nest.y);
  pad.receiveShadow = true;
  const hole = new THREE.Mesh(new THREE.CircleGeometry(nest.radius * 0.28, 24).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: GARDEN.hole }));
  hole.position.set(nest.x, NEST_TOP + 0.003, nest.y);
  // a ring of stones in the colony's colour
  const stones = Math.round(nest.radius * 15);
  const rng = seeded(nest.colony + 3);
  const ring = instanced(new THREE.IcosahedronGeometry(1, 2), new THREE.MeshStandardMaterial({ color: tint, roughness: 0.8 }), stones, (d, i) => {
    const a = (i / stones) * Math.PI * 2;
    const s = 0.1 + rng() * 0.05;
    d.position.set(nest.x + Math.cos(a) * nest.radius * 1.15, s * 0.3, nest.y + Math.sin(a) * nest.radius * 1.15);
    d.scale.set(s, s * 0.6, s);
  });
  ring.castShadow = ring.receiveShadow = true;
  scene.add(pad, hole, ring);
}

// curved blades that sway; the sway is a uniform the frame loop advances
function addGrass(scene: THREE.Object3D, info: WorldInfo, rng: () => number) {
  const h = 0.3;
  const blade = new THREE.PlaneGeometry(0.07, h, 1, 4).translate(0, h / 2, 0);
  const p = blade.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const k = p.getY(i) / h;
    p.setX(i, p.getX(i) * (1 - k * 0.92));
    p.setZ(i, k * k * 0.14);
  }
  blade.computeVertexNormals();
  const time = { value: 0 };
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.9, side: THREE.DoubleSide });
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = time;
    shader.vertexShader = 'uniform float uTime;\n' + shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>
      vec4 root = instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
      transformed.x += sin(uTime * 1.7 + root.x * 0.6 + root.z * 0.4) * 0.06 * position.y * position.y / ${(h * h).toFixed(3)};`);
  };
  scene.add(instanced(blade, mat, count(info, 4), (d) => {
    const [x, z] = inBed(rng, info, 1.2);
    d.position.set(x, 0, z);
    d.rotation.y = rng() * Math.PI * 2;
    d.scale.setScalar(0.5 + rng() * 1.1);
    return new THREE.Color(pick(rng, GARDEN.blades)).offsetHSL(0, 0, (rng() - 0.5) * 0.08).getHex();
  }));
  return time;
}

function addPebbles(scene: THREE.Object3D, info: WorldInfo, rng: () => number) {
  const pebbles = instanced(new THREE.IcosahedronGeometry(1, 2), new THREE.MeshStandardMaterial({ roughness: 0.85 }), count(info, 0.03), (d) => {
    const [x, z] = inBed(rng, info, 1.5);
    const s = 0.5 * (0.3 + rng() * rng() * 1.6);
    d.position.set(x, s * 0.15, z);
    d.rotation.set(rng() * 0.4, rng() * 3, rng() * 0.4);
    d.scale.set(s, s * (0.45 + rng() * 0.3), s * (0.7 + rng() * 0.3));
    return pick(rng, GARDEN.pebbles);
  });
  pebbles.castShadow = pebbles.receiveShadow = true;
  scene.add(pebbles);
}

// lollipop trees further out, round bushes nearer the hedge
function addTrees(scene: THREE.Object3D, info: WorldInfo, rng: () => number) {
  const trees = Array.from({ length: count(info, 0.012) }, () => [...inBed(rng, info, 3), 0.7 + rng() * 0.9]);
  const bushes = Array.from({ length: count(info, 0.02) }, () => [...inBed(rng, info, 1.6), 0.35 + rng() * 0.4]);
  const trunks = instanced(new THREE.CylinderGeometry(0.08, 0.12, 1.2, 8).translate(0, 0.6, 0),
    new THREE.MeshStandardMaterial({ color: GARDEN.bark, roughness: 0.9 }), trees.length, (d, i) => {
      const [x, z, s] = trees[i];
      d.position.set(x, 0, z);
      d.scale.setScalar(s);
    });
  const leafy = trees.length + bushes.length;
  const crowns = instanced(ball, new THREE.MeshStandardMaterial({ roughness: 0.8 }), leafy, (d, i) => {
    if (i < trees.length) {
      const [x, z, s] = trees[i];
      d.position.set(x, 1.5 * s, z);
      d.scale.set(0.75 * s, 0.7 * s, 0.75 * s);
    } else {
      const [x, z, s] = bushes[i - trees.length];
      d.position.set(x, s * 0.6, z);
      d.scale.set(s, s * 0.8, s);
    }
    return GARDEN.leaves[i % GARDEN.leaves.length];
  });
  trunks.castShadow = crowns.castShadow = true;
  scene.add(trunks, crowns);
}

function addFlowers(scene: THREE.Object3D, info: WorldInfo, rng: () => number) {
  const heads: [number, number, number][] = [];
  for (let i = count(info, 0.15); i > 0; i--) {
    const [x, z] = inBed(rng, info, 0.9);
    const colour = pick(rng, GARDEN.petals);
    for (let k = 0; k < 3 + rng() * 4; k++) heads.push([x + (rng() - 0.5) * 0.5, z + (rng() - 0.5) * 0.5, colour]);
  }
  scene.add(instanced(ball, new THREE.MeshStandardMaterial({ roughness: 0.6 }), heads.length, (d, i) => {
    const [x, z, colour] = heads[i];
    d.position.set(x, 0.1 + rng() * 0.08, z);
    d.scale.set(0.065, 0.04, 0.065);
    return colour;
  }));
}

// glass wall and dome on a white frame; the glass is front faces only, so a camera under it sees straight out.
// From outside, looking down more steeply than FADE_FROM (radians), the frame fades, almost gone by FADE_TO
const FADE_FROM = 0.45;
const FADE_TO = 0.65;
function addDome(scene: THREE.Object3D, info: WorldInfo) {
  const r = domeRadius(info);
  const glass = new THREE.MeshStandardMaterial({ color: GARDEN.glass, transparent: true, opacity: 0.08, roughness: 0.35, depthWrite: false });
  const frame = new THREE.MeshStandardMaterial({ color: GARDEN.frame, roughness: 0.45, metalness: 0.2 });
  const wall = new THREE.Mesh(new THREE.CylinderGeometry(r, r, WALL, 96, 1, true).translate(0, WALL / 2, 0), glass);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(r, 64, 24, 0, Math.PI * 2, 0, Math.PI / 2).translate(0, WALL, 0), glass);
  const curb = new THREE.Mesh(new THREE.TorusGeometry(r, 0.16, 8, 96).rotateX(Math.PI / 2), new THREE.MeshStandardMaterial({ color: GARDEN.curb, roughness: 0.9 }));
  curb.position.y = 0.06;
  const parts: THREE.Mesh[] = [curb];
  // offset half a step, so no rib lines up with a camera on an axis
  const ribs = 6;
  for (let i = 0; i < ribs; i++) {
    const arc = new THREE.Mesh(new THREE.TorusGeometry(r, 0.05, 6, 64, Math.PI), frame);
    arc.position.y = WALL;
    arc.rotation.y = ((i + 0.5) / ribs) * Math.PI;
    parts.push(arc);
  }
  for (let i = 0; i < ribs * 2; i++) {
    const a = ((i + 0.5) / (ribs * 2)) * Math.PI * 2;
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, WALL, 6).translate(0, WALL / 2, 0), frame);
    post.position.set(Math.cos(a) * r, 0, Math.sin(a) * r);
    parts.push(post);
  }
  for (const lat of [0, 0.45, 0.9]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r * Math.cos(lat), 0.05, 6, 96).rotateX(Math.PI / 2), frame);
    ring.position.y = WALL + r * Math.sin(lat);
    parts.push(ring);
  }
  for (const p of parts) p.castShadow = true;
  scene.add(...parts, wall, dome);
  // looking down on the dome from outside (the wide shot), its frame would cross the whole view: it fades to a trace,
  // and a low look from outside (the &intro opener) still shows it whole
  const top = new THREE.Vector3(0, WALL, 0);
  return (camera: THREE.Camera) => {
    const off = camera.position.clone().sub(top);
    const steep = off.length() > r ? Math.atan2(off.y, Math.hypot(off.x, off.z)) : 0;
    const opacity = 1 - 0.85 * THREE.MathUtils.smoothstep(steep, FADE_FROM, FADE_TO);
    if (Math.abs(opacity - frame.opacity) < 0.01) return;
    frame.opacity = opacity;
    frame.transparent = opacity < 1;
    frame.depthWrite = opacity >= 1;
  };
}

// boulders and pebbles on the plain, thinning out with distance
function addRocks(scene: THREE.Object3D, info: WorldInfo, rng: () => number) {
  const r0 = domeRadius(info) + 0.8, r1 = r0 + REACH;
  const n = Math.round(Math.PI * (r1 * r1 - r0 * r0) * 0.05);
  const rocks = instanced(new THREE.IcosahedronGeometry(1, 0), new THREE.MeshStandardMaterial({ roughness: 0.95, flatShading: true }), n, (d) => {
    const at = r0 + (r1 - r0) * rng() ** 1.6, a = rng() * Math.PI * 2;
    const s = 0.12 + rng() ** 4 * 1.8;
    d.position.set(Math.cos(a) * at, s * 0.2, Math.sin(a) * at);
    d.rotation.set(rng(), rng() * 3, rng());
    d.scale.set(s, s * (0.5 + rng() * 0.35), s * (0.7 + rng() * 0.4));
    return new THREE.Color(pick(rng, GARDEN.rocks)).offsetHSL(0, 0, (rng() - 0.5) * 0.06).getHex();
  });
  rocks.castShadow = rocks.receiveShadow = true;
  scene.add(rocks);
}

// flat-topped hills far out in the haze
function addMesas(scene: THREE.Object3D, rng: () => number) {
  const mat = new THREE.MeshStandardMaterial({ color: GARDEN.mesa, roughness: 1, flatShading: true });
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2 + rng() * 0.5, at = 55 + rng() * 20;
    const w = 6 + rng() * 9, h = 3 + rng() * 6;
    const mesa = new THREE.Mesh(new THREE.CylinderGeometry(w * 0.6, w, h, 7).translate(0, h / 2, 0), mat);
    mesa.position.set(Math.cos(a) * at, 0, Math.sin(a) * at);
    mesa.scale.z = 0.5 + rng() * 0.6;
    mesa.rotation.y = rng() * Math.PI;
    scene.add(mesa);
  }
}
