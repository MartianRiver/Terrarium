// Keeps scene objects in step with world frames. Frames arrive at the sim tick
// rate; rendering interpolates between the last two so motion stays smooth at
// any frame rate (and any replay speed later).

import * as THREE from 'three';
import { BlobView } from './blob';
import { Droppings } from './droppings';
import { Eggs } from './eggs';
import { type Box, Grips, type Holder } from './grips';
import { createLogger } from './lib/logger';
import { JellyPile } from './jelly';
import { Flags } from './flags';
import { Flowers } from './nectar';
import { BlockView, FoodView } from './props';
import type { Pose } from './sightfan';
import { Dust } from './sprint';
import { Tombstones } from './tombstones';
import type { CreatureState, Frame, WorldInfo } from './world';

const log = createLogger('worldview');

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerpAngle = (a: number, b: number, t: number) => a + Math.atan2(Math.sin(b - a), Math.cos(b - a)) * t;

function nearest(creatures: CreatureState[], at: { x: number; y: number }) {
  let best: CreatureState | undefined;
  let bestD = Infinity;
  for (const c of creatures) {
    const d = (c.x - at.x) ** 2 + (c.y - at.y) ** 2;
    if (d < bestD) [best, bestD] = [c, d];
  }
  return best;
}

export class WorldView {
  private blobs = new Map<number, BlobView>();
  private food = new Map<number, FoodView>();
  private dyingFood: FoodView[] = [];
  private blocks = new Map<number, BlockView>();
  private prevCreatures = new Map<number, CreatureState>();
  private prevBlocks = new Map<number, Frame['blocks'][number]>();
  private frame: Frame | null = null;
  // the Terrikin picked by clicking it (null: the first one), and where the followed one was last drawn
  chosen: number | null = null;
  // who to follow when nobody's chosen (the director's pick in a game; null: the first one)
  lead: number | null = null;
  // the ring under a chosen one; a reel's &pick follows without it
  marked = true;
  focus: Pose | null = null;
  focusId: number | null = null;
  private ring: THREE.Mesh;
  private droppings: Droppings | null;
  private scratch: CreatureState = { id: 0, colony: 0, x: 0, y: 0, heading: 0, speed: 0, size: 1, energy: 1, signal: -1, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1 };
  private piles = new Map<number, JellyPile>();
  private tombstones: Tombstones;
  private grips: Grips;
  private eggs: Eggs;
  private flowers: Flowers;
  private flags: Flags;
  private dust: Dust;

  constructor(private scene: THREE.Scene, private info: WorldInfo, droppings = true) {
    this.droppings = droppings ? new Droppings(scene, info.tickHz) : null;
    this.tombstones = new Tombstones(scene, info.tickHz);
    this.grips = new Grips(scene);
    this.eggs = new Eggs(scene, info.tickHz);
    this.flowers = new Flowers(scene, info.tickHz);
    this.flags = new Flags(scene);
    this.dust = new Dust(scene);
    this.ring = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.68, 40).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.8, depthWrite: false }));
    this.ring.position.y = 0.02;
    this.ring.visible = false;
    scene.add(this.ring);
    for (const nest of info.nests) {
      const pile = new JellyPile(nest);
      this.piles.set(nest.colony, pile);
      scene.add(pile.root);
    }
  }

  // call once per sim tick
  get current(): Frame | null {
    return this.frame;
  }

  push(frame: Frame) {
    if (this.frame) {
      this.prevCreatures = new Map(this.frame.creatures.map((c) => [c.id, c]));
      this.prevBlocks = new Map(this.frame.blocks.map((b) => [b.id, b]));
    }
    this.frame = frame;
    this.syncCreatures(frame);
    this.syncFood(frame);
    this.syncBlocks(frame);
    this.droppings?.push(frame);
    this.tombstones.push(frame);
    this.eggs.push(frame);
    this.flowers.push(frame);
    for (const [colony, pile] of this.piles) pile.update(frame.stores.find((s) => s.colony === colony)?.jelly ?? 0);
  }

  // alpha: 0..1 progress from the previous frame to the current one
  render(alpha: number, dt: number, time: number) {
    if (!this.frame) return;
    this.eggs.render(this.frame.tick, alpha, time);
    const holders: Holder[] = [];
    const poses = new Map<number, Pose>();
    // a chosen Terrikin that has left the world (its place taken by a hatchling) can't be followed
    if (this.chosen !== null && !this.blobs.has(this.chosen)) this.chosen = null;
    const followed = this.chosen ?? (this.lead !== null && this.blobs.has(this.lead) ? this.lead : this.frame.creatures[0]?.id);
    for (const c of this.frame.creatures) {
      const p = this.prevCreatures.get(c.id) ?? c;
      const s = this.scratch;
      Object.assign(s, c);
      s.x = lerp(p.x, c.x, alpha);
      s.y = lerp(p.y, c.y, alpha);
      s.heading = lerpAngle(p.heading, c.heading, alpha);
      s.speed = lerp(p.speed, c.speed, alpha);
      s.energy = lerp(p.energy, c.energy, alpha);
      // a signal changes where the bodies arrive, not as they set off: a tag lights the new it's bulb when they touch
      s.signal = p.signal;
      // drawn the size of its body, so bumping and tagging look like touching (the young too: their bodies are full size)
      s.size = c.size * this.eggs.growth(c.id, this.frame.tick, alpha);
      if (c.id === followed) {
        this.focus = { x: s.x, y: s.y, heading: s.heading };
        this.focusId = c.id;
        this.ring.position.x = s.x;
        this.ring.position.z = s.y;
      }
      const blob = this.blobs.get(c.id)!;
      // the dead are a tombstone now
      blob.root.visible = !this.tombstones.isDead(c.id);
      if (blob.root.visible) blob.update(s, this.info.maxSpeed, dt, time);
      if (blob.root.visible && blob.sprinting) this.dust.kick(c.id, s.x, s.y, s.heading, dt, time, c.nectar > 0);
      if (c.holding && blob.root.visible) holders.push({ x: s.x, y: s.y, colony: c.colony });
      poses.set(c.id, { x: s.x, y: s.y, heading: s.heading });
    }
    const boxes: Box[] = [];
    for (const b of this.frame.blocks) {
      const p = this.prevBlocks.get(b.id) ?? b;
      const box = { ...b, x: lerp(p.x, b.x, alpha), y: lerp(p.y, b.y, alpha), angle: lerpAngle(p.angle, b.angle, alpha) };
      this.blocks.get(b.id)!.update(box);
      boxes.push(box);
    }
    this.ring.visible = this.chosen !== null && this.marked;
    this.grips.update(holders, boxes);
    this.droppings?.render(this.frame.tick, alpha);
    this.tombstones.render(this.frame.tick, alpha);
    this.flowers.render(this.frame.tick, alpha, time);
    this.flags.render(this.frame.flags, poses, time);
    this.dust.render(dt);
    for (const f of this.food.values()) f.update(dt);
    this.dyingFood = this.dyingFood.filter((f) => {
      const alive = f.update(dt);
      if (!alive) this.scene.remove(f.root);
      return alive;
    });
  }

  // the Terrikin under a ray from the camera, or null
  pick(ray: THREE.Raycaster): number | null {
    const roots = new Map<THREE.Object3D, number>();
    for (const [id, blob] of this.blobs) if (blob.root.visible) roots.set(blob.root, id);
    for (const hit of ray.intersectObjects([...roots.keys()], true)) {
      for (let o: THREE.Object3D | null = hit.object; o; o = o.parent) {
        const id = roots.get(o);
        if (id !== undefined) return id;
      }
    }
    return null;
  }

  // take everything out of the scene, before a replay starts over or another opens
  dispose() {
    for (const blob of this.blobs.values()) {
      this.scene.remove(blob.root);
      blob.dispose();
    }
    for (const f of [...this.food.values(), ...this.dyingFood]) this.scene.remove(f.root);
    this.droppings?.clear();
    this.tombstones.clear();
    this.eggs.clear();
    this.flowers.clear();
    this.flags.clear();
    this.dust.clear();
    this.grips.clear();
    this.scene.remove(this.ring);
    this.ring.geometry.dispose();
    (this.ring.material as THREE.Material).dispose();
    for (const block of this.blocks.values()) {
      this.scene.remove(block.root);
      block.dispose();
    }
    for (const pile of this.piles.values()) {
      this.scene.remove(pile.root);
      pile.dispose();
    }
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
      const known = this.food.get(f.id);
      if (known) {
        known.sync(f);
        continue;
      }
      const view = new FoodView(f);
      this.food.set(f.id, view);
      this.scene.add(view.root);
    }
    for (const [id, view] of this.food) {
      if (seen.has(id)) continue;
      // food only goes when it's eaten, so the nearest creature had it
      const eater = nearest(frame.creatures, view.state);
      if (eater) this.droppings?.meal(eater.id, frame.tick);
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
