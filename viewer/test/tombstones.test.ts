// A tombstone goes where a creature fell, once per death, and fades in sim ticks;
// starting over (going back in time, or its arena resetting) leaves it alive again.

import * as THREE from 'three';
import { expect, test } from 'vitest';
import { Tombstones } from '../src/tombstones';
import type { Frame } from '../src/world';

const HZ = 20;
const blob = { id: 7, colony: 1, x: 3, y: 2, heading: 0, speed: 0, size: 1, energy: 0.5, signal: -1, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0 };
const frame = (tick: number, energy: number): Frame => ({ tick, creatures: [{ ...blob, energy }], food: [], blocks: [], stores: [], light: 1, eggs: [], flowers: [] });

test('one stone where it fell, which fades and goes', () => {
  const scene = new THREE.Scene();
  const t = new Tombstones(scene, HZ);
  t.push(frame(0, 0.1));
  expect(scene.children).toHaveLength(0);
  t.push(frame(1, 0));
  t.push(frame(2, 0));
  expect(scene.children).toHaveLength(1);
  expect(t.isDead(7)).toBe(true);
  const [stone] = scene.children;
  expect([stone.position.x, stone.position.z]).toEqual([blob.x, blob.y]);
  t.push(frame(1 + 30 * HZ, 0));
  expect(scene.children).toHaveLength(1);
  t.push(frame(2 + 30 * HZ, 0));
  expect(scene.children).toHaveLength(0);
  expect(t.isDead(7)).toBe(true);
});

test('alive again after its arena starts over or the replay goes back', () => {
  const scene = new THREE.Scene();
  const t = new Tombstones(scene, HZ);
  t.push(frame(10, 0));
  t.push(frame(11, 0.8));
  expect(t.isDead(7)).toBe(false);
  expect(scene.children).toHaveLength(1);
  t.push(frame(12, 0));
  expect(scene.children).toHaveLength(2);
  t.push(frame(0, 0.8));
  expect(scene.children).toHaveLength(0);
  expect(t.isDead(7)).toBe(false);
});
