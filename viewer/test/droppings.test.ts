// Droppings are timed in sim ticks, so a replay played at any speed (or the reel's
// fake clock) leaves the same ones, and starting over leaves none behind.

import * as THREE from 'three';
import { expect, test } from 'vitest';
import { Droppings } from '../src/droppings';
import type { Frame } from '../src/world';

const HZ = 20;
const blob = { id: 7, colony: 0, x: 3, y: 2, heading: 0, speed: 0, size: 1, energy: 0.9, signal: -1, carrying: 0, holding: 0, nectar: 0, sprinting: 0, load: 0, young: 0, stamina: 1, dung: 0 };
const frame = (tick: number): Frame => ({ tick, creatures: [blob], food: [], blocks: [], stores: [], light: 1, eggs: [], flowers: [], flags: [] });

test('every third meal leaves a dropping behind the blob, which later sinks away', () => {
  const scene = new THREE.Scene();
  const d = new Droppings(scene, HZ);
  d.meal(7, 0);
  d.meal(7, 10);
  d.push(frame(10 + 5 * HZ));
  expect(scene.children).toHaveLength(0);

  d.meal(7, 20);
  d.push(frame(20 + 5 * HZ - 1));
  expect(scene.children).toHaveLength(0);
  d.push(frame(20 + 5 * HZ));
  expect(scene.children).toHaveLength(1);
  const [drop] = scene.children;
  expect(drop.position.x).toBeLessThan(blob.x - 0.45); // heading +x, so behind is -x
  expect(drop.position.z).toBeCloseTo(blob.y);

  d.push(frame(20 + 5 * HZ + 42 * HZ + 1));
  expect(scene.children).toHaveLength(0);
});

test('going back in time clears them', () => {
  const scene = new THREE.Scene();
  const d = new Droppings(scene, HZ);
  for (let i = 0; i < 3; i++) d.meal(7, 0);
  d.push(frame(5 * HZ));
  expect(scene.children).toHaveLength(1);
  for (let i = 0; i < 2; i++) d.meal(7, 5 * HZ);
  d.push(frame(0));
  expect(scene.children).toHaveLength(0);
  d.meal(7, 1);
  d.push(frame(6 * HZ));
  expect(scene.children).toHaveLength(0);
});

test("in a world with droppings the sim's own are drawn, and none are made up after meals", () => {
  const scene = new THREE.Scene();
  const d = new Droppings(scene, HZ);
  for (let i = 0; i < 3; i++) d.meal(7, 0);
  d.push({ ...frame(5 * HZ), dung: [{ id: 1, x: 2, y: -3 }, { id: 2, x: -1, y: 4 }] });
  expect(scene.children).toHaveLength(2);
  expect(scene.children[0].position.x).toBe(2);
  expect(scene.children[0].position.z).toBe(-3);
  // picked up: it leaves the list, and goes until it's put down somewhere else
  d.push({ ...frame(5 * HZ + 1), dung: [{ id: 2, x: -1, y: 4 }] });
  expect(scene.children).toHaveLength(1);
  d.push({ ...frame(5 * HZ + 20), dung: [{ id: 2, x: -1, y: 4 }, { id: 1, x: 5, y: 5 }] });
  expect(scene.children.map((c) => c.position.x).sort()).toEqual([-1, 5]);
  d.push({ ...frame(0), dung: [] });
  expect(scene.children).toHaveLength(0);
});
