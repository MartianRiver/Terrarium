// One creature's look: a clay Terrikin. Everything here is procedural animation
// layered on top of the sim state; none of it feeds back into the sim.

import * as THREE from 'three';
import { COLONY_COLOURS, SIGNAL_COLOURS, SIGNAL_OFF_BULB, shimmer } from './palette';
import { berryGeo, berryMat, leafGeo, leafMat } from './props';
import { SIGNAL_OFF, type CreatureState } from './world';

// drawn at this scale its widest point (the arms) matches the sim's 0.45 m body
export const FIT = 0.79;

// a spline through the outline points, so the clay has no corners side-on
const EGG = new THREE.SplineCurve(
  [[0, 0], [0.2, 0.01], [0.36, 0.07], [0.46, 0.18], [0.5, 0.31], [0.47, 0.5], [0.37, 0.68], [0.2, 0.8], [0, 0.83]].map(([r, y]) => new THREE.Vector2(r, y)),
).getPoints(48).map((p) => new THREE.Vector2(Math.max(0, p.x), p.y));
const DEPTH = 0.93;

function eggRadius(y: number) {
  const i = EGG.findIndex((p) => p.y >= y);
  const [a, b] = [EGG[i - 1], EGG[i]];
  return a.x + ((b.x - a.x) * (y - a.y)) / (b.y - a.y);
}

// where the egg's front is at (x, y), and the tilt and turn that lay a feature flat on it
function onFront(x: number, y: number) {
  const z = (at: number) => Math.sqrt(eggRadius(at) ** 2 - x * x) * DEPTH;
  const front = z(y);
  return { z: front, tilt: Math.atan((z(y + 0.01) - z(y - 0.01)) / 0.02), turn: Math.atan((x * DEPTH * DEPTH) / front) };
}

// a feature sunk into the front so it can't stand off the curve when seen from the side
function seat(m: THREE.Mesh, x: number, y: number, proud: number, spin = 0) {
  const { z, tilt, turn } = onFront(x, y);
  m.position.set(x, y, z + proud);
  m.rotation.set(tilt, turn, spin, 'YXZ');
  return m;
}

// an egg, lighter on the front so the way it faces shows from overhead, darker underneath
const bodyGeo = (() => {
  const g = new THREE.LatheGeometry(EGG, 48);
  const p = g.attributes.position;
  const c = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) {
    const front = Math.min(1, Math.max(0, p.getZ(i) / 0.45));
    const under = 0.8 + 0.2 * Math.min(1, p.getY(i) / 0.35);
    c.fill((0.9 + 0.2 * front * front) * under, i * 3, i * 3 + 3);
  }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  return g;
})();
const ball = new THREE.SphereGeometry(1, 16, 12);
// rooted at its base, so it bends from where it joins the body
const tailGeo = new THREE.SphereGeometry(1, 12, 10).translate(0, 0.9, 0);
const stalkGeo = new THREE.CylinderGeometry(0.016, 0.026, 0.18, 6).translate(0, 0.09, 0);
const mouthGeo = new THREE.TorusGeometry(0.035, 0.011, 6, 14, Math.PI);
const dark = new THREE.MeshStandardMaterial({ color: 0x15151d, roughness: 0.2 });
const glintMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
const blushMat = new THREE.MeshStandardMaterial({ color: 0xff8ea0, roughness: 0.6, transparent: true, opacity: 0.75 });
const grey = new THREE.Color(0x8a8a90);

const SPRING_STEP = 1 / 60;
const LEGS = 0.1;
const BULB_GLOW = 0.8;
// energy where starving starts to show, and where full does
const HUNGRY_BELOW = 0.3;
const FULL_ABOVE = 0.85;
// a full crop shows as a glowing jelly belly, like a honeypot ant's; this many fills it
const CROP_FULL = 2;
const AMBER = new THREE.Color(0xffb03a);
const AMBER_GLOW = new THREE.Color(0xff8a1f);

function mesh(geo: THREE.BufferGeometry, mat: THREE.Material, pos: [number, number, number], scale: [number, number, number] | number, shadow = true) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(...pos);
  if (typeof scale === 'number') m.scale.setScalar(scale);
  else m.scale.set(...scale);
  m.castShadow = shadow;
  return m;
}

export class BlobView {
  readonly root = new THREE.Group();
  private body = new THREE.Group();
  private skin: THREE.MeshPhysicalMaterial;
  // arms and antenna have no vertex colours, so they get their own copy of the skin
  private limbs: THREE.MeshPhysicalMaterial;
  private bulbMat: THREE.MeshPhysicalMaterial;
  private tint: THREE.Color;
  private eyes: THREE.Mesh[] = [];
  private glints: THREE.Mesh[] = [];
  private arms: THREE.Mesh[] = [];
  private feet: THREE.Mesh[] = [];
  private stalk = new THREE.Group();
  private tail = new THREE.Group();
  private belly: THREE.Mesh;
  private bellyMat = new THREE.MeshPhysicalMaterial({
    color: 0xffb03a, emissive: 0xff8a1f, emissiveIntensity: 0.35, roughness: 0.15, clearcoat: 1, transparent: true, opacity: 0.85,
  });
  private crop = 0;
  // a berry carried in its jaws (carry), held up on top of its head like an ant's seed
  private berry = new THREE.Group();
  private carried = 0;
  private mouth: THREE.Mesh;
  private blush: THREE.Mesh[] = [];
  // nectar: a shimmering bulb and belly and a happy face; sprinting: stretched out and quick-footed
  private joy = 0;
  private dash = 0;
  private sheen = new THREE.Color();

  private seed = Math.random() * 100;
  private phase = 0;
  private stride = 0;
  private squash = 0;
  private squashVel = 0;
  private lean = 0;
  private lastYaw: number | null = null;
  private turn = 0;
  private blinkIn = 1 + Math.random() * 3;
  private blinkLeft = 0;
  private glow = SIGNAL_OFF_BULB.clone();
  // shown energy eases toward the sim's, so a meal visibly fills the blob out
  private energy: number | null = null;
  private hunger = 0;
  private full = 0;

  constructor(colony: number) {
    this.tint = COLONY_COLOURS[colony % COLONY_COLOURS.length].clone().offsetHSL(0, -0.05, 0.04);
    this.skin = new THREE.MeshPhysicalMaterial({
      color: this.tint.clone(), roughness: 0.78, sheen: 0.9, sheenRoughness: 0.5, sheenColor: new THREE.Color(0xffffff),
    });
    this.limbs = this.skin.clone();
    this.skin.vertexColors = true;
    this.bulbMat = new THREE.MeshPhysicalMaterial({
      color: SIGNAL_OFF_BULB.clone(), emissive: SIGNAL_OFF_BULB.clone(), emissiveIntensity: 0, roughness: 0.25, clearcoat: 1, clearcoatRoughness: 0.05,
    });

    this.body.add(mesh(bodyGeo, this.skin, [0, 0, 0], [1, 1, DEPTH]));
    this.body.position.y = LEGS;

    this.mouth = seat(mesh(mouthGeo, dark, [0, 0, 0], 1, false), 0, 0.41, 0.004, Math.PI);
    this.body.add(this.mouth);
    for (const side of [-1, 1]) {
      const eye = seat(mesh(ball, dark, [0, 0, 0], [0.052, 0.085, 0.035]), side * 0.14, 0.52, 0.012);
      const glint = mesh(ball, glintMat, [0.3, 0.35, 0.8], 0.3, false);
      eye.add(glint);
      this.eyes.push(eye);
      this.glints.push(glint);
      this.body.add(eye);

      const blush = seat(mesh(ball, blushMat, [0, 0, 0], [0.055, 0.032, 0.02], false), side * 0.25, 0.44, 0.006);
      this.blush.push(blush);
      this.body.add(blush);

      const arm = mesh(ball, this.limbs, [side * 0.43, 0.36, 0.04], [0.08, 0.13, 0.08]);
      this.arms.push(arm);
      this.body.add(arm);

      const foot = mesh(ball, new THREE.MeshPhysicalMaterial({ color: this.tint.clone().multiplyScalar(0.82), roughness: 0.78 }),
        [side * 0.23, 0.065, 0.17], [0.13, 0.07, 0.2]);
      this.feet.push(foot);
      this.root.add(foot);
    }

    // the colony shows on the tail, which hunger never greys
    this.tail.position.set(0, 0.26, -0.37);
    this.tail.add(mesh(tailGeo, new THREE.MeshStandardMaterial({ color: this.tint.clone().offsetHSL(0, 0.18, -0.14), roughness: 0.6 }), [0, 0, 0], [0.065, 0.15, 0.065]));
    this.body.add(this.tail);

    this.belly = seat(mesh(ball, this.bellyMat, [0, 0, 0], [0.2, 0.15, 0.06], false), 0, 0.2, -0.02);
    this.belly.visible = false;
    this.body.add(this.belly);

    this.stalk.position.set(0, 0.79, -0.03);
    this.stalk.add(mesh(stalkGeo, this.limbs, [0, 0, 0], 1), mesh(ball, this.bulbMat, [0, 0.23, 0], 0.105));
    this.body.add(this.stalk);

    // in front of the antenna, sitting on the crown; sized to match the berries on the ground
    const held = mesh(berryGeo, berryMat, [0, 0, 0], 1.25);
    const leaf = mesh(leafGeo, leafMat, [0.04, 0.12, -0.02], 1.1);
    leaf.rotation.set(0.3, 0.6, 0.2);
    this.berry.add(held, leaf);
    this.berry.position.set(0, 0.92, 0.12);
    this.berry.visible = false;
    this.body.add(this.berry);

    this.root.add(this.body);
  }

  update(s: CreatureState, maxSpeed: number, dt: number, time: number) {
    const yaw = Math.PI / 2 - s.heading;
    this.root.position.set(s.x, 0, s.y);
    this.root.rotation.y = yaw;
    this.root.scale.setScalar(s.size * FIT);

    // turn rate drives lean and where the eyes look
    if (this.lastYaw !== null && dt > 0) {
      const dYaw = Math.atan2(Math.sin(yaw - this.lastYaw), Math.cos(yaw - this.lastYaw));
      this.turn += (dYaw / dt - this.turn) * Math.min(1, dt * 8);
    }
    this.lastYaw = yaw;

    const ease = Math.min(1, dt * 6);
    this.joy += (s.nectar > 0 ? 1 - this.joy : -this.joy) * ease;
    this.dash += (s.sprinting > 0 ? 1 - this.dash : -this.dash) * ease;
    this.applyEnergy(s.energy, dt);
    this.animateWalk(s.speed / maxSpeed, dt, time);
    this.animateEyes(dt, time);
    this.applySignal(s.signal, dt);
    this.applyCrop(s.carrying, dt);
    this.applyNectar(time);
    this.applyLoad(s.load, dt);
  }

  // picked up with a little pop, set down quickly
  private applyLoad(load: number, dt: number) {
    this.carried += ((load > 0 ? 1 : 0) - this.carried) * Math.min(1, dt * (load > 0 ? 10 : 18));
    this.berry.visible = this.carried > 0.02;
    this.berry.scale.setScalar(this.carried);
  }

  get sprinting() {
    return this.dash > 0.5;
  }

  private animateWalk(moving: number, dt: number, time: number) {
    moving = Math.min(1, Math.max(0, moving));
    // a starving blob shuffles
    const spring = 1 - this.hunger * 0.6;
    this.stride += ((moving > 0.08 ? (0.5 + moving * 0.5) * spring : 0) - this.stride) * Math.min(1, dt * 6);

    const before = Math.floor(this.phase / Math.PI);
    if (this.stride > 0.02) this.phase += dt * (7 + 7 * moving) * (1 + 0.7 * this.dash);
    // a little squash on each footfall
    if (Math.floor(this.phase / Math.PI) !== before) this.squashVel -= 0.8 * this.stride;

    const bob = Math.abs(Math.sin(this.phase)) * this.stride * 0.22;
    const breathe = Math.sin(time * 2.2 + this.seed) * 0.025 * (1 - this.stride);
    const hop = this.joy * 0.05 * Math.abs(Math.sin(time * 8 + this.seed));
    const target = bob * 0.12 + breathe + hop;
    // the spring is stiff: stepped in one go at 10 fps it grows every frame instead of settling
    for (let left = dt; left > 0; left -= SPRING_STEP) {
      const h = Math.min(left, SPRING_STEP);
      this.squashVel += ((target - this.squash) * 220 - this.squashVel * 14) * h;
      this.squash += this.squashVel * h;
    }

    const sy = 1 + this.squash;
    const girth = 1 + this.full * 0.08 - this.hunger * 0.12;
    // never wider than the body it's drawn in
    const sxz = Math.min(1.04, girth / Math.sqrt(Math.max(0.5, sy)));
    this.body.scale.set(sxz * (1 - 0.06 * this.dash), sy * (1 - 0.1 * this.dash), sxz * (1 + 0.14 * this.dash));
    this.body.position.y = LEGS + bob * 0.16;

    // waddle: lean into the walk, rock side to side with each step
    this.lean += ((moving * 0.08 + this.dash * 0.16) - this.lean) * Math.min(1, dt * 5);
    this.body.rotation.x = this.lean;
    const rock = Math.sin(this.phase) * 0.11 * this.stride;
    this.body.rotation.z = Math.max(-0.15, Math.min(0.15, -this.turn * 0.08 + rock));

    this.arms.forEach((arm, i) => {
      arm.rotation.z = (i ? 1 : -1) * 0.2 * (1 - this.hunger * 0.7);
      // arms swing against the feet
      arm.rotation.x = Math.cos(this.phase + (i + 1) * Math.PI) * 0.6 * this.stride;
    });
    this.feet.forEach((foot, i) => {
      foot.position.y = 0.065 + Math.max(0, Math.sin(this.phase + i * Math.PI)) * 0.075 * this.stride;
      foot.position.z = 0.17 + Math.cos(this.phase + i * Math.PI) * 0.11 * this.stride;
    });

    this.stalk.rotation.z = Math.sin(time * 3 + this.seed) * 0.08 + this.turn * 0.05;
    this.stalk.rotation.x = 0.3 + this.hunger * 0.9;
    // the tail wags with the steps, idles slowly and droops when starving
    this.tail.rotation.y = Math.sin(this.phase * 2) * 0.45 * this.stride + Math.sin(time * 1.7 + this.seed) * 0.15;
    this.tail.rotation.x = -0.4 + this.hunger * 0.9;
  }

  private animateEyes(dt: number, time: number) {
    this.blinkIn -= dt;
    if (this.blinkIn <= 0) {
      this.blinkLeft = 0.13;
      this.blinkIn = 2 + Math.random() * 4;
    }
    this.blinkLeft = Math.max(0, this.blinkLeft - dt);
    // heavy lids when starving
    const open = 0.085;
    // happy eyes squeeze up into crescents
    const eyeHeight = (this.blinkLeft > 0 ? open * 0.12 : open * (1 - this.hunger * 0.5)) * (1 - 0.6 * this.joy);

    // the glints lead into the turn, with a little idle wander
    const lookX = (Math.max(-0.35, Math.min(0.35, -this.turn * 0.15)) + Math.sin(time * 0.7 + this.seed) * 0.08) * 0.15;
    const lookY = Math.sin(time * 0.5 + this.seed * 2) * 0.015;
    for (let i = 0; i < 2; i++) {
      this.eyes[i].scale.y = eyeHeight;
      this.glints[i].position.x = 0.3 + lookX;
      this.glints[i].position.y = 0.35 + lookY;
    }
  }

  private applyEnergy(energy: number, dt: number) {
    this.energy = this.energy === null ? energy : this.energy + (energy - this.energy) * Math.min(1, dt * 4);
    const e = this.energy;
    this.hunger = Math.min(1, Math.max(0, (HUNGRY_BELOW - e) / HUNGRY_BELOW));
    this.full = Math.min(1, Math.max(0, (e - FULL_ABOVE) / (1 - FULL_ABOVE)));
    // duller as energy falls, grey when starving
    this.skin.color.copy(this.tint).lerp(grey, (1 - e) * 0.3 + this.hunger * 0.45);
    this.limbs.color.copy(this.skin.color);
  }

  private applyCrop(carrying: number, dt: number) {
    this.crop += (Math.min(1, carrying / CROP_FULL) - this.crop) * Math.min(1, dt * 6);
    this.belly.visible = this.crop > 0.02;
    this.belly.scale.set(0.2 * this.crop, 0.15 * this.crop, 0.06);
  }

  private applyNectar(time: number) {
    const j = this.joy;
    this.mouth.scale.set(1 + 0.7 * j, 1 + 1.1 * j, 1);
    for (const b of this.blush) b.scale.set(0.055 * (1 + 0.5 * j), 0.032 * (1 + 0.5 * j), 0.02);
    shimmer(time, this.seed, this.sheen);
    if (j > 0.01) {
      this.bulbMat.color.lerp(this.sheen, j);
      this.bulbMat.emissive.copy(this.bulbMat.color);
      this.bulbMat.emissiveIntensity = Math.max(this.bulbMat.emissiveIntensity, j * 1.2);
    }
    this.bellyMat.color.copy(AMBER).lerp(this.sheen, j);
    this.bellyMat.emissive.copy(AMBER_GLOW).lerp(this.sheen, j);
    const fill = Math.max(this.crop, j * 0.75);
    this.belly.visible = fill > 0.02;
    this.belly.scale.set(0.2 * fill, 0.15 * fill, 0.06);
  }

  private applySignal(signal: number, dt: number) {
    const on = signal !== SIGNAL_OFF;
    this.glow.lerp(on ? SIGNAL_COLOURS[signal] : SIGNAL_OFF_BULB, Math.min(1, dt * 14));
    this.bulbMat.color.copy(this.glow);
    this.bulbMat.emissive.copy(this.glow);
    this.bulbMat.emissiveIntensity += ((on ? BULB_GLOW : 0) - this.bulbMat.emissiveIntensity) * Math.min(1, dt * 14);
  }

  dispose() {
    this.root.traverse((o) => {
      if (!(o instanceof THREE.Mesh)) return;
      const m = o.material as THREE.Material;
      if (m !== dark && m !== glintMat && m !== blushMat) m.dispose();
    });
  }
}
