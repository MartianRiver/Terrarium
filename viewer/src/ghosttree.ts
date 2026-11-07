// The ghost tree: a faint see-through tree where a nim's notes put the tree, from the sim's readout of its memory
// (terrarium/ghost.py, a replay's `ghosts`), not where the tree is. The sim only writes it for the moment after the
// nim comes up from unloading an apple, which is the only moment the readout was checked; this just draws what's
// there, fading in as it appears and out as it goes, with a small label so nobody takes it for the real tree.

import * as THREE from 'three';
import { treeModel } from './tree';
import type { Frame } from './world';

const PEAK = 0.3;
const FADE = 0.5; // seconds in and out
const LABEL = 'where its notes put the tree';
const LABEL_AT = 3.6;

function labelTexture() {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 72;
  const g = c.getContext('2d')!;
  g.fillStyle = 'rgba(255,255,255,0.88)';
  g.beginPath();
  g.roundRect(2, 2, 508, 68, 34);
  g.fill();
  g.fillStyle = '#2b2b3d';
  g.font = '700 38px system-ui, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(LABEL, 256, 38);
  return new THREE.CanvasTexture(c);
}

// a soft dark patch for the ground under it
function shadowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d')!;
  const fill = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  fill.addColorStop(0, 'rgba(0,0,0,0.5)');
  fill.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = fill;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

interface Ghost {
  root: THREE.Group;
  patch: THREE.PlaneGeometry;
  body: THREE.MeshBasicMaterial;
  shadow: THREE.MeshBasicMaterial;
  label: THREE.SpriteMaterial;
  level: number; // 0..1, how far faded in
  on: boolean;
}

export class GhostTrees {
  private ghosts = new Map<number, Ghost>();
  private labelMap = labelTexture();
  private shadowMap = shadowTexture();

  constructor(private scene: THREE.Scene) {}

  // call once per sim tick
  push(frame: Frame) {
    const now = new Set<number>();
    for (const g of frame.ghosts ?? []) {
      now.add(g.id);
      const ghost = this.ghosts.get(g.id) ?? this.make(g.id);
      ghost.on = true;
      ghost.root.position.set(g.x, 0, g.y);
    }
    for (const [id, ghost] of this.ghosts) if (!now.has(id)) ghost.on = false;
  }

  render(dt: number) {
    for (const [id, ghost] of this.ghosts) {
      ghost.level = Math.min(1, Math.max(0, ghost.level + (ghost.on ? dt : -dt) / FADE));
      ghost.root.visible = ghost.level > 0;
      ghost.body.opacity = PEAK * ghost.level;
      ghost.shadow.opacity = ghost.level;
      ghost.label.opacity = ghost.level;
      if (!ghost.on && ghost.level === 0) this.drop(id);
    }
  }

  clear() {
    for (const id of [...this.ghosts.keys()]) this.drop(id);
    this.labelMap.dispose();
    this.shadowMap.dispose();
  }

  private make(id: number): Ghost {
    const body = new THREE.MeshBasicMaterial({ color: 0xcfe6ff, transparent: true, opacity: 0, depthWrite: false });
    const shadow = new THREE.MeshBasicMaterial({ map: this.shadowMap, transparent: true, opacity: 0, depthWrite: false });
    const label = new THREE.SpriteMaterial({ map: this.labelMap, transparent: true, opacity: 0, depthWrite: false, fog: false, toneMapped: false });
    const root = new THREE.Group();
    root.add(treeModel(body, body, false));
    const patchGeo = new THREE.PlaneGeometry(2.4, 2.4).rotateX(-Math.PI / 2);
    const patch = new THREE.Mesh(patchGeo, shadow);
    patch.position.y = 0.02;
    const tag = new THREE.Sprite(label);
    tag.scale.set(3.4, 3.4 * 72 / 512, 1);
    tag.position.y = LABEL_AT;
    root.add(patch, tag);
    root.visible = false;
    this.scene.add(root);
    const ghost = { root, patch: patchGeo, body, shadow, label, level: 0, on: true };
    this.ghosts.set(id, ghost);
    return ghost;
  }

  private drop(id: number) {
    const ghost = this.ghosts.get(id)!;
    this.scene.remove(ghost.root);
    // the tree's geometry is shared with the real tree's, so only the patch is ours
    ghost.patch.dispose();
    ghost.body.dispose();
    ghost.shadow.dispose();
    ghost.label.dispose();
    this.ghosts.delete(id);
  }
}
