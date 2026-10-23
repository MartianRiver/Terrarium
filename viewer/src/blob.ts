// One creature's look. Everything here is procedural animation layered on top of
// the sim state; none of it feeds back into the sim.

import * as THREE from 'three';
import { COLONY_COLOURS, SIGNAL_COLOURS, SIGNAL_DARK } from './palette';
import { SIGNAL_OFF, type CreatureState } from './world';

const sphere = new THREE.SphereGeometry(1, 32, 20);
const smallSphere = new THREE.SphereGeometry(1, 14, 10);
const stalkGeo = new THREE.CylinderGeometry(0.018, 0.028, 0.26, 6).translate(0, 0.13, 0);
const eyeMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.25 });
const pupilMat = new THREE.MeshStandardMaterial({ color: 0x15151d, roughness: 0.15 });
const grey = new THREE.Color(0x8a8a90);

const HOP_HEIGHT = 0.16;
const HOP_RATE = 11; // rad/s at full speed
// energy where starving starts to show, and where full does
const HUNGRY_BELOW = 0.3;
const FULL_ABOVE = 0.85;

function mesh(geo: THREE.BufferGeometry, mat: THREE.Material, pos: [number, number, number], scale: [number, number, number]) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(...pos);
  m.scale.set(...scale);
  m.castShadow = true;
  return m;
}

export class BlobView {
  readonly root = new THREE.Group();
  private body = new THREE.Group();
  private bodyMat: THREE.MeshPhysicalMaterial;
  private bulbMat: THREE.MeshStandardMaterial;
  private tint: THREE.Color;
  private eyes: THREE.Mesh[] = [];
  private pupils: THREE.Mesh[] = [];
  private arms: THREE.Mesh[] = [];
  private feet: THREE.Mesh[] = [];
  private stalk: THREE.Mesh;

  private seed = Math.random() * 100;
  private phase = 0;
  private hopAmp = 0;
  private squash = 0;
  private squashVel = 0;
  private lean = 0;
  private lastYaw: number | null = null;
  private turn = 0;
  private blinkIn = 1 + Math.random() * 3;
  private blinkLeft = 0;
  private glow = new THREE.Color();
  // shown energy eases toward the sim's, so a meal visibly fills the blob out
  private energy: number | null = null;
  private hunger = 0;
  private full = 0;

  constructor(colony: number) {
    this.tint = COLONY_COLOURS[colony % COLONY_COLOURS.length];
    this.bodyMat = new THREE.MeshPhysicalMaterial({
      color: this.tint.clone(), roughness: 0.45, clearcoat: 0.6, clearcoatRoughness: 0.3,
      sheen: 0.4, sheenColor: new THREE.Color(0xffffff), emissive: this.tint.clone(),
    });
    this.bulbMat = new THREE.MeshStandardMaterial({ color: SIGNAL_DARK.clone(), emissive: SIGNAL_DARK.clone(), roughness: 0.3 });

    this.body.add(mesh(sphere, this.bodyMat, [0, 0.5, 0], [0.42, 0.5, 0.4]));

    for (const side of [-1, 1]) {
      const eye = mesh(smallSphere, eyeMat, [side * 0.15, 0.64, 0.33], [0.1, 0.12, 0.08]);
      const pupil = mesh(smallSphere, pupilMat, [0, 0, 0.75], [0.5, 0.5, 0.4]);
      pupil.castShadow = false;
      eye.add(pupil);
      this.eyes.push(eye);
      this.pupils.push(pupil);
      this.body.add(eye);

      const arm = mesh(smallSphere, this.bodyMat, [side * 0.4, 0.42, 0.02], [0.08, 0.14, 0.08]);
      this.arms.push(arm);
      this.body.add(arm);

      const foot = mesh(smallSphere, this.bodyMat, [side * 0.16, 0.05, 0.06], [0.12, 0.06, 0.16]);
      this.feet.push(foot);
      this.root.add(foot);
    }

    this.stalk = mesh(stalkGeo, this.bodyMat, [0, 0.96, -0.04], [1, 1, 1]);
    this.stalk.rotation.x = -0.25;
    this.stalk.add(mesh(smallSphere, this.bulbMat, [0, 0.3, 0], [0.09, 0.09, 0.09]));
    this.body.add(this.stalk);

    this.root.add(this.body);
  }

  update(s: CreatureState, maxSpeed: number, dt: number, time: number) {
    const yaw = Math.PI / 2 - s.heading;
    this.root.position.set(s.x, 0, s.y);
    this.root.rotation.y = yaw;
    this.root.scale.setScalar(s.size);

    // turn rate drives lean and where the eyes look
    if (this.lastYaw !== null && dt > 0) {
      const dYaw = Math.atan2(Math.sin(yaw - this.lastYaw), Math.cos(yaw - this.lastYaw));
      this.turn += (dYaw / dt - this.turn) * Math.min(1, dt * 8);
    }
    this.lastYaw = yaw;

    this.applyEnergy(s.energy, dt);
    this.animateHop(s.speed / maxSpeed, dt, time);
    this.animateEyes(dt, time);
    this.applySignal(s.signal, dt);
  }

  private animateHop(moving: number, dt: number, time: number) {
    moving = Math.min(1, Math.max(0, moving));
    // a starving blob drags itself along
    const spring = 1 - this.hunger * 0.6;
    this.hopAmp += ((moving > 0.08 ? (0.5 + moving * 0.5) * spring : 0) - this.hopAmp) * Math.min(1, dt * 6);

    const before = Math.floor(this.phase / Math.PI);
    if (this.hopAmp > 0.02) this.phase += dt * HOP_RATE * (0.6 + 0.4 * moving);
    // squash on each landing
    if (Math.floor(this.phase / Math.PI) !== before) this.squashVel -= 3.2 * this.hopAmp;

    const air = Math.abs(Math.sin(this.phase)) * this.hopAmp;
    const breathe = Math.sin(time * 2.2 + this.seed) * 0.025 * (1 - this.hopAmp);
    const target = air * 0.12 + breathe;
    this.squashVel += ((target - this.squash) * 220 - this.squashVel * 14) * dt;
    this.squash += this.squashVel * dt;

    const sy = 1 + this.squash;
    const girth = 1 + this.full * 0.14 - this.hunger * 0.12;
    const sxz = girth / Math.sqrt(Math.max(0.5, sy));
    this.body.scale.set(sxz, sy, sxz);
    this.body.position.y = air * HOP_HEIGHT;

    this.lean += ((moving * 0.18) - this.lean) * Math.min(1, dt * 5);
    this.body.rotation.x = this.lean;
    this.body.rotation.z = Math.max(-0.25, Math.min(0.25, -this.turn * 0.08));

    const flap = (0.25 + air * 0.9) * (1 - this.hunger * 0.7);
    this.arms[0].rotation.z = -flap;
    this.arms[1].rotation.z = flap;
    this.stalk.rotation.z = Math.sin(time * 3 + this.seed) * 0.08 + this.turn * 0.05;
    this.stalk.rotation.x = this.hunger * 0.9;

    this.feet.forEach((foot, i) => {
      const step = Math.sin(this.phase + i * Math.PI) * this.hopAmp;
      foot.position.z = 0.06 + step * 0.08;
      foot.position.y = 0.05 + air * HOP_HEIGHT * 0.5;
    });
  }

  private animateEyes(dt: number, time: number) {
    this.blinkIn -= dt;
    if (this.blinkIn <= 0) {
      this.blinkLeft = 0.13;
      this.blinkIn = 2 + Math.random() * 4;
    }
    this.blinkLeft = Math.max(0, this.blinkLeft - dt);
    // heavy lids when starving
    const eyeHeight = this.blinkLeft > 0 ? 0.015 : 0.12 - this.hunger * 0.06;

    // pupils lead into the turn, with a little idle wander
    const lookX = Math.max(-0.35, Math.min(0.35, -this.turn * 0.15)) + Math.sin(time * 0.7 + this.seed) * 0.08;
    const lookY = Math.sin(time * 0.5 + this.seed * 2) * 0.1;
    for (let i = 0; i < 2; i++) {
      this.eyes[i].scale.y = eyeHeight;
      this.pupils[i].position.x = lookX;
      this.pupils[i].position.y = lookY;
    }
  }

  private applyEnergy(energy: number, dt: number) {
    this.energy = this.energy === null ? energy : this.energy + (energy - this.energy) * Math.min(1, dt * 4);
    const e = this.energy;
    this.hunger = Math.min(1, Math.max(0, (HUNGRY_BELOW - e) / HUNGRY_BELOW));
    this.full = Math.min(1, Math.max(0, (e - FULL_ABOVE) / (1 - FULL_ABOVE)));
    // duller as energy falls, grey when starving; full ones glow
    this.bodyMat.color.copy(this.tint).lerp(grey, (1 - e) * 0.35 + this.hunger * 0.4);
    this.bodyMat.emissiveIntensity = 0.03 + e * 0.2 + this.full * 0.15;
  }

  private applySignal(signal: number, dt: number) {
    const on = signal !== SIGNAL_OFF;
    const target = on ? SIGNAL_COLOURS[signal] : SIGNAL_DARK;
    this.glow.lerp(target, Math.min(1, dt * 14));
    this.bulbMat.color.copy(this.glow);
    this.bulbMat.emissive.copy(this.glow);
    this.bulbMat.emissiveIntensity += ((on ? 3.2 : 0.15) - this.bulbMat.emissiveIntensity) * Math.min(1, dt * 14);
  }

  dispose() {
    this.bodyMat.dispose();
    this.bulbMat.dispose();
  }
}
