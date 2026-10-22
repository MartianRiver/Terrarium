// Keeps scene objects in step with world frames. Frames arrive at the sim tick
// rate; rendering interpolates between the last two so motion stays smooth at
// any frame rate (and any replay speed later).

import type * as THREE from 'three';
import { BlobView } from './blob';
import { createLogger } from './lib/logger';
import { BlockView, FoodView } from './props';
import type { CreatureState, Frame, WorldInfo } from './world';

const log = createLogger('worldview');

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerpAngle = (a: number, b: number, t: number) => a + Math.atan2(Math.sin(b - a), Math.cos(b - a)) * t;

export class WorldView {
  private blobs = new Map<number, BlobView>();
  private food = new Map<number, FoodView>();
  private dyingFood: FoodView[] = [];
  private blocks = new Map<number, BlockView>();
  private prevCreatures = new Map<number, CreatureState>();
  private prevBlocks = new Map<number, Frame['blocks'][number]>();
  private frame: Frame | null = null;
  private scratch: CreatureState = { id: 0, colony: 0, x: 0, y: 0, heading: 0, speed: 0, size: 1, energy: 1, signal: -1 };

  constructor(private scene: THREE.Scene, private info: WorldInfo) {}

  // call once per sim tick
  push(frame: Frame) {
    if (this.frame) {
      this.prevCreatures = new Map(this.frame.creatures.map((c) => [c.id, c]));
      this.prevBlocks = new Map(this.frame.blocks.map((b) => [b.id, b]));
    }
    this.frame = frame;
    this.syncCreatures(frame);
    this.syncFood(frame);
    this.syncBlocks(frame);
  }

  // alpha: 0..1 progress from the previous frame to the current one
  render(alpha: number, dt: number, time: number) {
    if (!this.frame) return;
    for (const c of this.frame.creatures) {
      const p = this.prevCreatures.get(c.id) ?? c;
      const s = this.scratch;
      Object.assign(s, c);
      s.x = lerp(p.x, c.x, alpha);
      s.y = lerp(p.y, c.y, alpha);
      s.heading = lerpAngle(p.heading, c.heading, alpha);
      s.speed = lerp(p.speed, c.speed, alpha);
      s.energy = lerp(p.energy, c.energy, alpha);
      this.blobs.get(c.id)!.update(s, this.info.maxSpeed, dt, time);
    }
    for (const b of this.frame.blocks) {
      const p = this.prevBlocks.get(b.id) ?? b;
      this.blocks.get(b.id)!.update({ ...b, x: lerp(p.x, b.x, alpha), y: lerp(p.y, b.y, alpha), angle: lerpAngle(p.angle, b.angle, alpha) });
    }
    for (const f of this.food.values()) f.update(dt, time);
    this.dyingFood = this.dyingFood.filter((f) => {
      const alive = f.update(dt, time);
      if (!alive) this.scene.remove(f.root);
      return alive;
    });
  }

  get creatureCount() {
    return this.frame?.creatures.length ?? 0;
  }

  private syncCreatures(frame: Frame) {
    const seen = new Set<number>();
    for (const c of frame.creatures) {
      seen.add(c.id);
      if (this.blobs.has(c.id)) continue;
      const blob = new BlobView(c.colony);
      this.blobs.set(c.id, blob);
      this.scene.add(blob.root);
      log.trace('creature added', { id: c.id, colony: c.colony });
    }
    for (const [id, blob] of this.blobs) {
      if (seen.has(id)) continue;
      this.scene.remove(blob.root);
      blob.dispose();
      this.blobs.delete(id);
      log.debug('creature removed', { id });
    }
  }

  private syncFood(frame: Frame) {
    const seen = new Set<number>();
    for (const f of frame.food) {
      seen.add(f.id);
      if (this.food.has(f.id)) continue;
      const view = new FoodView(f);
      this.food.set(f.id, view);
      this.scene.add(view.root);
    }
    for (const [id, view] of this.food) {
      if (seen.has(id)) continue;
      view.despawn();
      this.dyingFood.push(view);
      this.food.delete(id);
    }
  }

  private syncBlocks(frame: Frame) {
    for (const b of frame.blocks) {
      if (this.blocks.has(b.id)) continue;
      const view = new BlockView(b);
      this.blocks.set(b.id, view);
      this.scene.add(view.root);
    }
    // blocks don't get destroyed in any stage yet
  }
}
