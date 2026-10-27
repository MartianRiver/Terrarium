// &ant: a sketch of an ant for this world, built the way it would have to be to learn to walk and
// balance: rigid parts joined by motorised hinges (three on each leg: hip swing, hip lift, knee), feet that
// know when they touch, and a centre of mass that has to stay over the feet. J shows the parts a trainer
// would see. The tripod gait is hand-made, only to show the body moving; a trained ant would find its own.
// Viewer only: the sim's physics is flat, so nothing there has legs yet.

import * as THREE from 'three';
import { COLONY_COLOURS } from './palette';

// metres, like the sim: nose to tail about a Terrikin and a half
const HIP = 0.3; // thorax height standing
const COXA = 0.07;
const FEMUR = 0.3;
const TIBIA = 0.36;
const PERIOD = 0.9; // seconds a stride
const LIFT = 0.12;
const SPEED = 0.5;
const LOOP = 2.4; // radius of the loop it walks round the middle

// body-frame: +x forward, +y up, ±z the sides
const LEGS = [
  { name: 'front', root: [0.12, 0.0, 0.07], rest: [0.42, 0.42], tripod: 0 },
  { name: 'middle', root: [0.0, -0.01, 0.08], rest: [0.02, 0.5], tripod: 1 },
  { name: 'hind', root: [-0.11, 0.0, 0.07], rest: [-0.4, 0.44], tripod: 0 },
] as const;
// kg, for the centre of mass: what the parts would weigh at this size
const MASS = { head: 0.15, thorax: 0.3, gaster: 0.4, leg: 0.025 };

interface Leg {
  root: THREE.Vector3;
  rest: THREE.Vector3;
  offset: number;
  hip: THREE.Group;
  femur: THREE.Group;
  tibia: THREE.Group;
  pad: THREE.Mesh;
  at: THREE.Vector3; // the foot, in the world
  from: THREE.Vector3;
  down: boolean;
}

const capsule = (r: number, len: number) => new THREE.CapsuleGeometry(r, len, 4, 10).rotateZ(-Math.PI / 2).translate(len / 2, 0, 0);
const ball = new THREE.SphereGeometry(1, 20, 14);

export class AntStudy {
  readonly root = new THREE.Group();
  private body = new THREE.Group();
  private head = new THREE.Group();
  private gaster = new THREE.Group();
  private legs: Leg[] = [];
  private overlay = new THREE.Group();
  private hull: THREE.LineLoop;
  private com: THREE.Mesh;
  private plumb: THREE.Line;
  private joints: THREE.Mesh[] = [];
  private antennae: THREE.Group[] = [];
  private time = 0;
  private started = false;
  private panel: HTMLElement;
  private readout: HTMLElement;
  focus = { x: 0, y: 0 };

  constructor(private scene: THREE.Scene, colony = 0) {
    const tint = COLONY_COLOURS[colony % COLONY_COLOURS.length].clone().offsetHSL(0, -0.05, -0.02);
    const skin = new THREE.MeshPhysicalMaterial({ color: tint, roughness: 0.7, sheen: 0.9, sheenRoughness: 0.5, sheenColor: new THREE.Color(0xffffff) });
    const darker = skin.clone();
    darker.color = tint.clone().multiplyScalar(0.8);
    const dark = new THREE.MeshStandardMaterial({ color: 0x2a211d, roughness: 0.3 });
    const glint = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const part = (geo: THREE.BufferGeometry, mat: THREE.Material, at: number[], scale: number | number[]) => {
      const m = new THREE.Mesh(geo, mat);
      m.position.set(at[0], at[1], at[2]);
      if (typeof scale === 'number') m.scale.setScalar(scale);
      else m.scale.set(scale[0], scale[1], scale[2]);
      m.castShadow = true;
      return m;
    };

    this.body.add(part(ball, skin, [0.02, 0, 0], [0.2, 0.11, 0.115]));
    this.body.add(part(ball, darker, [-0.19, 0.01, 0], [0.05, 0.05, 0.05]));
    this.gaster.position.set(-0.22, 0.02, 0);
    this.gaster.add(part(ball, skin, [-0.24, 0.04, 0], [0.27, 0.19, 0.2]));
    this.body.add(this.gaster);

    // a round, Terrikin-like face: big dark eyes with a glint, small mandibles
    this.head.position.set(0.24, 0.06, 0);
    this.head.add(part(ball, skin, [0.07, 0, 0], [0.15, 0.13, 0.14]));
    for (const side of [-1, 1]) {
      const eye = part(ball, dark, [0.16, 0.035, side * 0.075], [0.04, 0.055, 0.035]);
      eye.add(part(ball, glint, [0.35, 0.35, 0.3], 0.3));
      this.head.add(eye);
      const jaw = part(capsule(0.016, 0.07), darker, [0.2, -0.06, side * 0.04], 1);
      jaw.rotation.y = -side * 0.7;
      this.head.add(jaw);
      // elbowed antennae, scape then funiculus, with the colony's bulb at the tip
      const scape = new THREE.Group();
      scape.position.set(0.17, 0.08, side * 0.04);
      scape.rotation.set(side * -0.5, side * 0.3, 1.0);
      scape.add(part(capsule(0.013, 0.16), darker, [0, 0, 0], 1));
      const funiculus = new THREE.Group();
      funiculus.position.x = 0.16;
      funiculus.rotation.z = -1.5;
      funiculus.add(part(capsule(0.011, 0.2), darker, [0, 0, 0], 1));
      funiculus.add(part(ball, new THREE.MeshPhysicalMaterial({ color: 0xffe28a, emissive: 0xffc94d, emissiveIntensity: 0.6, clearcoat: 1, roughness: 0.2 }), [0.21, 0, 0], 0.03));
      scape.add(funiculus);
      this.antennae.push(funiculus);
      this.head.add(scape);
    }
    this.body.add(this.head);

    const joint = (colour: number) => {
      const m = new THREE.Mesh(ball, new THREE.MeshBasicMaterial({ color: colour, depthTest: false, transparent: true, opacity: 0.75 }));
      m.scale.setScalar(0.022);
      m.renderOrder = 10;
      this.joints.push(m);
      return m;
    };
    for (const spec of LEGS) {
      for (const side of [-1, 1]) {
        const hip = new THREE.Group();
        hip.position.set(spec.root[0], spec.root[1], spec.root[2] * side);
        hip.add(part(capsule(0.03, COXA), skin, [0, 0, 0], 1));
        hip.add(joint(0xd8d8d8));
        const femur = new THREE.Group();
        femur.position.x = COXA;
        femur.add(part(capsule(0.026, FEMUR), skin, [0, 0, 0], 1), joint(0xd8d8d8));
        const tibia = new THREE.Group();
        tibia.position.x = FEMUR;
        tibia.add(part(capsule(0.02, TIBIA), darker, [0, 0, 0], 1), joint(0xffd23f));
        // its own material, lit while the foot is down
        const pad = part(ball, darker.clone(), [TIBIA, 0, 0], 0.035);
        tibia.add(pad);
        femur.add(tibia);
        hip.add(femur);
        this.body.add(hip);
        // tripods: left front, right middle and left hind step together, then the other three
        const offset = ((spec.tripod + (side > 0 ? 1 : 0)) % 2) * 0.5;
        this.legs.push({
          root: hip.position.clone(), rest: new THREE.Vector3(spec.rest[0], -HIP, spec.rest[1] * side), offset,
          hip, femur, tibia, pad, at: new THREE.Vector3(), from: new THREE.Vector3(), down: true,
        });
      }
    }
    this.root.add(this.body);

    // what training would watch: the feet that are down, the shape they hold up, and the centre of mass over it
    this.hull = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(Array.from({ length: 6 }, () => new THREE.Vector3())),
      new THREE.LineBasicMaterial({ color: 0x4dffb8, depthTest: false, transparent: true }));
    this.com = new THREE.Mesh(ball, new THREE.MeshBasicMaterial({ color: 0x4dffb8, depthTest: false, transparent: true }));
    this.com.scale.setScalar(0.035);
    this.plumb = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
      new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 0.03, gapSize: 0.02, depthTest: false, transparent: true }));
    for (const o of [this.hull, this.com, this.plumb]) o.renderOrder = 10;
    this.overlay.add(this.hull, this.com, this.plumb);
    scene.add(this.root, this.overlay);

    this.panel = document.createElement('aside');
    this.panel.className = 'ant-study';
    this.panel.setAttribute('aria-label', 'Ant study');
    this.panel.innerHTML = `
      <h2>An ant that could learn to walk</h2>
      <p><b>Body</b>: head, thorax, petiole and gaster, and six legs of coxa, femur and tibia: 22 rigid parts, each with a mass.</p>
      <p><b>Motors</b>: 18, three a leg (hip swing, hip lift, knee), each with a range and a strength limit. A brain would set a target angle for each.</p>
      <p><b>Senses</b>: each joint's angle and speed, which feet touch (green), and the thorax's tilt and spin, like an inner ear.</p>
      <p><b>Balance</b>: the green outline is what the feet down hold up; the dot under the dashed line is the centre of mass. Outside the outline, it tips.</p>
      <p class="live"></p>
      <p class="small">The tripod gait here is made by hand to show the body. A trained ant would find its own, paid for moving and for staying upright, in a 3D physics sim: the one the Terrikins live in is flat. J hides the markers.</p>`;
    this.readout = this.panel.querySelector('.live')!;
    document.body.append(this.panel);
  }

  set marked(on: boolean) {
    this.overlay.visible = on;
    for (const j of this.joints) j.visible = on;
  }

  get marked() {
    return this.overlay.visible;
  }

  update(dt: number) {
    this.time += dt;
    const t = this.time;
    const a = (SPEED * t) / LOOP;
    const ahead = new THREE.Vector3(-Math.sin(a), 0, Math.cos(a));
    // a stride's two tripods each lift the body a little as they push off
    const bob = Math.cos((4 * Math.PI * t) / PERIOD);
    this.body.position.set(LOOP * Math.cos(a), HIP + 0.012 * bob, LOOP * Math.sin(a));
    this.body.rotation.set(0.03 * Math.sin((2 * Math.PI * t) / PERIOD), Math.atan2(-ahead.z, ahead.x), -0.02 * bob, 'YXZ');
    this.gaster.rotation.z = 0.18 + 0.03 * bob;
    this.head.rotation.y = 0.12 * Math.sin(t * 0.9);
    for (const [i, f] of this.antennae.entries()) f.rotation.z = -1.5 + 0.15 * Math.sin(t * 3 + i * 1.7);
    this.body.updateMatrixWorld(true);
    this.focus = { x: this.body.position.x, y: this.body.position.z };

    // where a foot lands so that it's under its rest spot halfway through being down
    const stride = SPEED * PERIOD;
    const landing = (leg: Leg, early: number) => this.body.localToWorld(leg.rest.clone()).setY(0).addScaledVector(ahead, stride * early);
    for (const leg of this.legs) {
      const phase = (t / PERIOD + leg.offset) % 1;
      const down = phase < 0.5;
      if (!this.started) {
        leg.at.copy(landing(leg, down ? 0.25 - phase : -0.25));
        leg.from.copy(leg.at);
      } else if (down && !leg.down) {
        leg.at.y = 0;
      } else if (!down && leg.down) {
        leg.from.copy(leg.at);
      }
      if (!down && this.started) {
        const u = (phase - 0.5) / 0.5;
        leg.at.lerpVectors(leg.from, landing(leg, 0.25), u * u * (3 - 2 * u));
        leg.at.y = LIFT * Math.sin(Math.PI * u);
      }
      leg.down = down;
      this.reach(leg);
      (leg.pad.material as THREE.MeshPhysicalMaterial).emissive.setHex(down && this.overlay.visible ? 0x1fae6c : 0x000000);
    }
    this.started = true;
    this.balance();
  }

  // the three hinge angles that put a foot where it should be: a turn at the hip, then a two-link reach
  private reach(leg: Leg) {
    const d = this.body.worldToLocal(leg.at.clone()).sub(leg.root);
    leg.hip.rotation.y = Math.atan2(-d.z, d.x);
    const h = Math.hypot(d.x, d.z) - COXA;
    const far = THREE.MathUtils.clamp(Math.hypot(h, d.y), Math.abs(FEMUR - TIBIA) + 0.01, FEMUR + TIBIA - 0.001);
    const lift = Math.acos((FEMUR * FEMUR + far * far - TIBIA * TIBIA) / (2 * FEMUR * far));
    leg.femur.rotation.z = Math.atan2(d.y, h) + lift;
    leg.tibia.rotation.z = Math.acos((FEMUR * FEMUR + TIBIA * TIBIA - far * far) / (2 * FEMUR * TIBIA)) - Math.PI;
  }

  private balance() {
    const v = new THREE.Vector3();
    const com = new THREE.Vector3();
    let total = 0;
    const add = (o: THREE.Object3D, local: number[], kg: number) => {
      com.addScaledVector(o.localToWorld(v.set(local[0], local[1], local[2])), kg);
      total += kg;
    };
    add(this.body, [0.02, 0, 0], MASS.thorax);
    add(this.head, [0.07, 0, 0], MASS.head);
    add(this.gaster, [-0.24, 0.04, 0], MASS.gaster);
    for (const leg of this.legs) add(leg.tibia, [0, 0, 0], MASS.leg * 3);
    com.divideScalar(total);

    const feet = this.legs.filter((l) => l.down).map((l) => new THREE.Vector2(l.at.x, l.at.z));
    const mid = feet.reduce((s, p) => s.add(p), new THREE.Vector2()).divideScalar(Math.max(feet.length, 1));
    feet.sort((p, q) => Math.atan2(p.y - mid.y, p.x - mid.x) - Math.atan2(q.y - mid.y, q.x - mid.x));
    // how far inside the outline the centre of mass is (negative: outside)
    const c = new THREE.Vector2(com.x, com.z);
    let margin = feet.length < 3 ? -1 : Infinity;
    for (let i = 0; i < feet.length && feet.length >= 3; i++) {
      const p = feet[i];
      const q = feet[(i + 1) % feet.length];
      const edge = q.clone().sub(p);
      margin = Math.min(margin, edge.cross(c.clone().sub(p)) / edge.length());
    }
    const steady = margin > 0;
    const colour = steady ? 0x4dffb8 : 0xff4f6b;

    const pts = this.hull.geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < 6; i++) {
      const p = feet[Math.min(i, feet.length - 1)] ?? c;
      pts.setXYZ(i, p.x, 0.015, p.y);
    }
    pts.needsUpdate = true;
    (this.hull.material as THREE.LineBasicMaterial).color.setHex(colour);
    (this.com.material as THREE.MeshBasicMaterial).color.setHex(colour);
    this.com.position.set(com.x, 0.015, com.z);
    const line = this.plumb.geometry.attributes.position as THREE.BufferAttribute;
    line.setXYZ(0, com.x, com.y, com.z);
    line.setXYZ(1, com.x, 0.015, com.z);
    line.needsUpdate = true;
    this.plumb.computeLineDistances();

    const tilt = THREE.MathUtils.radToDeg(Math.hypot(this.body.rotation.x, this.body.rotation.z));
    this.readout.textContent = `Now: ${feet.length} feet down · centre of mass ${steady ? `${(margin * 100).toFixed(0)} cm inside` : 'outside'} · tilt ${tilt.toFixed(1)}°`;
  }

  dispose() {
    this.scene.remove(this.root, this.overlay);
    this.panel.remove();
  }
}
