// Costumes for Catch them!: what the child can be, put on a Terrikin when it's made. Each only adds to or recolours
// the clay; the walk, eyes and antenna stay a Terrikin's, so it moves like everyone else.
import * as THREE from 'three';
import { ball, BlobView, DEPTH, eggRadius, hornGeo, mesh, seat } from './blob';

export type Costume = 'panda' | 'dragon' | 'dino' | 'penguin' | 'cheetah';

const clay = (color: number, roughness = 0.78) =>
  new THREE.MeshPhysicalMaterial({ color, roughness, sheen: 0.6, sheenColor: new THREE.Color(0xffffff) });

// somewhere on the egg's skin: up `y` and round `around` radians from the front (π is the back), lying flat on it
function onSkin(m: THREE.Mesh, y: number, around: number, proud = 0.004) {
  const r = eggRadius(y) + proud;
  m.position.set(Math.sin(around) * r, y, Math.cos(around) * r * DEPTH);
  m.rotation.set(0, around, 0);
  return m;
}

// spikes or a fin down the back, from the top of the head to the tail
function ridge(b: BlobView, mat: THREE.Material, count: number, size: number, flat = 1) {
  for (let i = 0; i < count; i++) {
    const k = i / (count - 1);
    const y = 0.8 - k * 0.55;
    const spike = mesh(hornGeo, mat, [0, y, -eggRadius(Math.min(y, 0.78)) * DEPTH + 0.01], [size * flat, size, size]);
    spike.rotation.x = -0.4 - k * 1.1;
    b.body.add(spike);
  }
}

// dots scattered over the sides and back, the same ones every time
function spots(b: BlobView, mat: THREE.Material, count: number, size: number, low = 0.2, high = 0.72, front = 0.9) {
  let s = 7;
  const next = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  for (let i = 0; i < count; i++) {
    const y = low + next() * (high - low);
    const around = (next() < 0.5 ? -1 : 1) * (front + next() * (Math.PI - front));
    const r = size * (0.7 + next() * 0.6);
    b.body.add(onSkin(mesh(ball, mat, [0, 0, 0], [r, r * 0.85, 0.012], false), y, around));
  }
}

function belly(b: BlobView, color: number, scale: [number, number, number], y: number) {
  b.body.add(seat(mesh(ball, clay(color, 0.75), [0, 0, 0], scale, false), 0, y, -0.01));
}

function feet(b: BlobView, color: number) {
  const mat = clay(color);
  for (const foot of b.feet) foot.material = mat;
}

function recolourTail(b: BlobView, color: number) {
  b.tail.traverse((o) => {
    if (o instanceof THREE.Mesh) (o.material as THREE.MeshStandardMaterial).color.set(color);
  });
}

// a bat's wing: a bone along the top and a scalloped edge between three fingers, pivoting at the shoulder, swept back
// and tilted up, so it reads as a wing from above as well as from the side
const wingGeo = (() => {
  const s = new THREE.Shape();
  s.moveTo(0, 0);
  s.quadraticCurveTo(0.14, 0.2, 0.36, 0.2);
  s.quadraticCurveTo(0.3, 0.08, 0.31, -0.02);
  s.quadraticCurveTo(0.25, 0.04, 0.2, -0.04);
  s.quadraticCurveTo(0.15, 0.02, 0.1, -0.05);
  s.quadraticCurveTo(0.05, 0, 0, 0);
  return new THREE.ExtrudeGeometry(s, { depth: 0.015, bevelEnabled: true, bevelSize: 0.008, bevelThickness: 0.006, bevelSegments: 2 }).translate(0, 0, -0.0075);
})();
const boneGeo = new THREE.CylinderGeometry(0.014, 0.01, 1, 6).rotateZ(-Math.PI / 2).translate(0.5, 0, 0);

function wings(b: BlobView, skin: THREE.Material, bone: THREE.Material) {
  for (const side of [-1, 1]) {
    const shoulder = new THREE.Group();
    shoulder.position.set(side * 0.3, 0.56, -0.24);
    shoulder.rotation.y = side * 0.75;
    const wing = new THREE.Group();
    wing.scale.x = side;
    wing.add(mesh(wingGeo, skin, [0, 0, 0], 1), mesh(boneGeo, bone, [0, 0.01, 0], [0.37, 1, 1]));
    wing.children[1].rotation.z = 0.5;
    shoulder.add(wing);
    b.wings.push(wing);
    b.body.add(shoulder);
  }
}

// white, with black ears, arms, feet and antenna, and black patches a little below and outside the eyes, so the eyes
// and their glints still show
function panda(b: BlobView) {
  const black = 0x2a2930;
  b.tint.set(0xf4f1ea);
  b.dark = true;
  b.limbs.color.set(black);
  feet(b, black);
  const mat = clay(black, 0.8);
  for (const side of [-1, 1]) {
    b.body.add(mesh(ball, mat, [side * 0.27, 0.74, -0.04], [0.11, 0.11, 0.07]));
    b.body.add(seat(mesh(ball, mat, [0, 0, 0], [0.09, 0.11, 0.025], false), side * 0.17, 0.49, 0.002, side * 0.5));
  }
}

// a baby dragon: green, a pale belly, two nubby horns, spikes down its back, an orange tail and golden wings
function dragon(b: BlobView) {
  const horn = new THREE.MeshStandardMaterial({ color: 0xf7a440, roughness: 0.5 });
  b.tint.set(0x6cc35a);
  belly(b, 0xf6e27a, [0.24, 0.2, 0.04], 0.24);
  feet(b, 0x4f9a40);
  for (const side of [-1, 1]) {
    const h = mesh(hornGeo, horn, [side * 0.13, 0.8, -0.02], 1);
    h.rotation.set(-0.35, 0, -side * 0.35);
    b.body.add(h);
  }
  wings(b, new THREE.MeshPhysicalMaterial({ color: 0xf7c95a, roughness: 0.6, side: THREE.DoubleSide, sheen: 0.4 }), horn);
  ridge(b, horn, 3, 0.8);
  recolourTail(b, 0xf7a440);
}

// a baby dinosaur in a brown and mint T-shirt's colours: brown, a cream belly, mint spikes down its back and mint
// spots on its sides, big round eyes, a wide grin and a thick tail
function dino(b: BlobView) {
  const mint = clay(0x84d9c4, 0.6);
  b.tint.set(0x8b7565);
  belly(b, 0xefe5d3, [0.22, 0.16, 0.04], 0.2);
  feet(b, 0x6f5c4f);
  const white = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
  for (const eye of b.eyes) eye.add(mesh(ball, white, [0, 0, -0.4], [1.9, 1.3, 0.5], false));
  b.mouth.scale.set(2.2, 1.4, 1.2);
  ridge(b, mint, 5, 1.25);
  spots(b, mint, 7, 0.045, 0.22, 0.6, 1.0);
  // thick and straight out behind (the tail's own tilt is the walk's)
  b.tail.children[0].scale.set(0.13, 0.3, 0.13);
  b.tail.children[0].rotation.x = -1.1;
  recolourTail(b, 0x8b7565);
}

// a baby penguin: navy with a white front, flippers, an orange beak and orange feet
function penguin(b: BlobView) {
  b.tint.set(0x2e3647);
  b.body.add(seat(mesh(ball, clay(0xf7f6f0, 0.7), [0, 0, 0], [0.3, 0.32, 0.03], false), 0, 0.36, -0.02));
  feet(b, 0xf5a23a);
  for (const arm of b.arms) arm.scale.set(0.05, 0.17, 0.1);
  const beak = seat(mesh(hornGeo, clay(0xf5a23a, 0.5), [0, 0, 0], [1.1, 1.0, 0.8], false), 0, 0.44, 0.0);
  beak.rotation.x += Math.PI / 2 + 0.25;
  b.body.add(beak);
  b.mouth.visible = false;
  recolourTail(b, 0x232a38);
}

// a baby cheetah: golden with dark spots, a pale muzzle, round ears, black tear lines from its eyes and a ringed tail
function cheetah(b: BlobView) {
  const dark = clay(0x3a2a1a, 0.8);
  b.tint.set(0xf0b44a);
  feet(b, 0xd99a35);
  b.body.add(seat(mesh(ball, clay(0xfbf1dc, 0.75), [0, 0, 0], [0.13, 0.08, 0.03], false), 0, 0.42, -0.008));
  for (const side of [-1, 1]) {
    b.body.add(mesh(ball, clay(0xf0b44a), [side * 0.25, 0.76, -0.04], [0.09, 0.09, 0.05]));
    b.body.add(mesh(ball, dark, [side * 0.25, 0.765, -0.01], [0.05, 0.05, 0.03], false));
    b.body.add(seat(mesh(ball, dark, [0, 0, 0], [0.012, 0.06, 0.01], false), side * 0.12, 0.45, 0.004, side * 0.35));
  }
  spots(b, dark, 18, 0.03, 0.15, 0.78, 0.7);
  recolourTail(b, 0xf0b44a);
  const tail = b.tail.children[0];
  for (const [y, s] of [[0.06, 1.05], [0.14, 1.0], [0.22, 0.9]]) {
    tail.add(mesh(ball, dark, [0, 0.9 + (y - 0.15) / 0.15, 0], [1.05 * s, 0.12, 1.05 * s], false));
  }
}

const COSTUMES: Record<Costume, (b: BlobView) => void> = { panda, dragon, dino, penguin, cheetah };

export function dress(b: BlobView, costume: Costume) {
  COSTUMES[costume](b);
}
