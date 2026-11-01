// An egg sits where it was laid until its Terrikin hatches, then cracks and the hatchling (the egg's id) grows from
// small to full size; an egg nobody hatches shrinks away; going back in time forgets them all.

import * as THREE from 'three';
import { expect, test } from 'vitest';
import { Eggs } from '../src/eggs';
import type { CreatureState, EggState, Frame } from '../src/world';

const HZ = 20;
const egg: EggState = { id: 40, colony: 1, x: 2, y: -1, progress: 0.5 };
const blob: CreatureState = { id: 40, colony: 1, x: 2, y: -1, heading: 0, speed: 0, size: 1, energy: 0.8, signal: -1, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1, dung: 0 };
const frame = (tick: number, eggs: EggState[], creatures: CreatureState[] = []): Frame =>
  ({ tick, creatures, food: [], blocks: [], stores: [], light: 1, eggs, flowers: [], flags: [] });

test('an egg hatches into the Terrikin with its id, which grows to full size', () => {
  const scene = new THREE.Scene();
  const eggs = new Eggs(scene, HZ);
  eggs.push(frame(0, [egg]));
  expect(eggs.count).toBe(1);
  const [laid] = scene.children;
  expect([laid.position.x, laid.position.z]).toEqual([egg.x, egg.y]);
  eggs.push(frame(1, [], [blob]));
  expect(eggs.count).toBe(0);
  const small = eggs.growth(40, 1, 0);
  expect(small).toBeGreaterThan(0.3);
  expect(small).toBeLessThan(0.5);
  expect(eggs.growth(40, 1 + HZ, 0)).toBeGreaterThan(small);
  expect(eggs.growth(40, 1 + 2 * HZ, 0)).toBe(1);
  expect(eggs.growth(99, 1, 0)).toBe(1);
  // the shell's halves fly and go
  eggs.render(1 + HZ, 0, 0);
  expect(scene.children).toHaveLength(0);
});

test('an egg nobody hatches shrinks away, and going back forgets every egg', () => {
  const scene = new THREE.Scene();
  const eggs = new Eggs(scene, HZ);
  eggs.push(frame(10, [egg]));
  eggs.push(frame(11, []));
  expect(eggs.growth(40, 11, 0)).toBe(1);
  eggs.render(11 + HZ, 0, 0);
  expect(scene.children).toHaveLength(0);
  eggs.push(frame(12, [egg]));
  eggs.push(frame(0, []));
  expect(eggs.count).toBe(0);
  expect(scene.children).toHaveLength(0);
});
