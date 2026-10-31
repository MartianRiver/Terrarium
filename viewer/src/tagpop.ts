// Tag, drawn: a soft glow on the ground under whoever's it, so it reads at a glance (the bulb alone is small on a
// phone), and at a tag a ring and a puff of sparkles in the bulb's colour where the two touched. Read off the frames
// (the bulb moving from one Terrikin to another), so it's look only; timed on the wall clock like the dust. With a
// cone (degrees), the it also shows how much it can see as a fan on the ground, so its blind spot shows.

import * as THREE from 'three';
import { SIGNAL_COLOURS } from './palette';
import type { Pose } from './sightfan';
import type { Frame } from './world';

const IT = 0; // the it's signal in tag (replay.py)
const LIFE = 0.7;
const TOUCH = 1.2; // centres closer than this: they touched (two bodies of 0.45 m), so the bulb moving is a tag
const SPARKS = 9;
// a bulb lit this long on one Terrikin means a game of tag (the demo flashes the same colour for a second)
const GAME = 1.5;
const sparkGeo = new THREE.OctahedronGeometry(0.075);
const CONE_REACH = 2.4; // the fan is drawn this far out, well short of what it really sees
const ringGeo = new THREE.RingGeometry(0.8, 1, 40).rotateX(-Math.PI / 2);

// a disc that fades from the bulb's colour at the middle to nothing at the edge
function glowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d')!;
  const fill = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  fill.addColorStop(0, 'rgba(255,255,255,0.9)');
  fill.addColorStop(0.55, 'rgba(255,255,255,0.45)');
  fill.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = fill;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

interface Spark { mesh: THREE.Mesh; vx: number; vy: number; vz: number; spin: number }
interface Pop { ring: THREE.Mesh; sparks: Spark[]; mat: THREE.MeshBasicMaterial; age: number }

export class TagPops {
  private pops: Pop[] = [];
  private it = -1;
  private held = 0;
  private game = false;
  private glow: THREE.Mesh;
  private fan: THREE.Mesh | null = null;

  constructor(private scene: THREE.Scene, cone = 0) {
    if (cone > 0) {
      const a = (cone * Math.PI) / 180;
      // a circle sector centred on +x (heading 0), laid on the ground
      const geo = new THREE.CircleGeometry(CONE_REACH, 48, -a / 2, a).rotateX(-Math.PI / 2);
      this.fan = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.22, depthWrite: false }));
      this.fan.position.y = 0.02;
      this.fan.visible = false;
      scene.add(this.fan);
    }
    const mat = new THREE.MeshBasicMaterial({ color: SIGNAL_COLOURS[IT], map: glowTexture(), transparent: true, opacity: 0.6,
      depthWrite: false, blending: THREE.AdditiveBlending });
    this.glow = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 2.2).rotateX(-Math.PI / 2), mat);
    this.glow.position.y = 0.025;
    this.glow.visible = false;
    scene.add(this.glow);
  }

  // call once per sim tick: the first frame of an episode sets who's it without a pop
  push(frame: Frame, first: boolean, tickHz: number) {
    const now = frame.creatures.find((c) => c.signal === IT);
    const was = frame.creatures.find((c) => c.id === this.it);
    if (now && was && now.id !== this.it && !first && Math.hypot(now.x - was.x, now.y - was.y) < TOUCH) {
      this.pop((now.x + was.x) / 2, (now.y + was.y) / 2);
    }
    this.held = now && now.id === this.it ? this.held + 1 : 0;
    if (this.held >= GAME * tickHz) this.game = true;
    this.it = now ? now.id : -1;
  }

  private pop(x: number, y: number) {
    const mat = new THREE.MeshBasicMaterial({ color: SIGNAL_COLOURS[IT], transparent: true, opacity: 1, depthWrite: false });
    const ring = new THREE.Mesh(ringGeo, mat);
    ring.position.set(x, 0.03, y);
    this.scene.add(ring);
    const sparks: Spark[] = [];
    for (let i = 0; i < SPARKS; i++) {
      const a = (i / SPARKS) * Math.PI * 2 + Math.random() * 0.5;
      const mesh = new THREE.Mesh(sparkGeo, mat);
      mesh.position.set(x, 0.55, y);
      this.scene.add(mesh);
      const out = 1.4 + Math.random() * 0.8;
      sparks.push({ mesh, vx: Math.cos(a) * out, vy: 1.6 + Math.random() * 0.8, vz: Math.sin(a) * out, spin: 4 + Math.random() * 6 });
    }
    this.pops.push({ ring, sparks, mat, age: 0 });
  }

  // shown: who the viewer draws as it (the bulb moves on when the bodies arrive, a tick after the sim's tag)
  render(dt: number, poses: Map<number, Pose>, shown: number, time: number) {
    const at = poses.get(shown);
    this.glow.visible = this.game && at !== undefined;
    if (this.fan) {
      this.fan.visible = this.game && at !== undefined;
      if (at) {
        this.fan.position.set(at.x, 0.02, at.y);
        // sim heading turns from +x towards +y, which is +z here
        this.fan.rotation.y = -at.heading;
      }
    }
    if (at) {
      this.glow.position.x = at.x;
      this.glow.position.z = at.y;
      (this.glow.material as THREE.MeshBasicMaterial).opacity = 0.5 + 0.12 * Math.sin(time * 5);
    }
    this.pops = this.pops.filter((p) => {
      p.age += dt;
      const t = Math.min(p.age / LIFE, 1);
      p.ring.scale.setScalar(0.3 + 1.1 * (1 - (1 - t) ** 3));
      p.mat.opacity = 1 - t * t;
      for (const s of p.sparks) {
        s.vy -= 5 * dt;
        s.mesh.position.x += s.vx * dt;
        s.mesh.position.y = Math.max(0.05, s.mesh.position.y + s.vy * dt);
        s.mesh.position.z += s.vz * dt;
        s.mesh.rotation.y += s.spin * dt;
        s.mesh.scale.setScalar(1 - 0.5 * t);
      }
      if (t < 1) return true;
      this.remove(p);
      return false;
    });
  }

  clear() {
    for (const p of this.pops) this.remove(p);
    this.pops = [];
    this.it = -1;
    this.held = 0;
    this.game = false;
    this.glow.visible = false;
    if (this.fan) this.fan.visible = false;
  }

  dispose() {
    this.clear();
    this.scene.remove(this.glow);
    this.glow.geometry.dispose();
    if (this.fan) {
      this.scene.remove(this.fan);
      this.fan.geometry.dispose();
      (this.fan.material as THREE.Material).dispose();
    }
    const mat = this.glow.material as THREE.MeshBasicMaterial;
    mat.map?.dispose();
    mat.dispose();
  }

  private remove(p: Pop) {
    this.scene.remove(p.ring);
    for (const s of p.sparks) this.scene.remove(s.mesh);
    p.mat.dispose();
  }
}
