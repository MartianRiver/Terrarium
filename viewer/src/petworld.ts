import * as THREE from 'three';
import { createStage } from './stage';
import { WorldView } from './worldview';
import { isAsleep, type Care, type CareAction } from './petcare';
import type { CreatureState, Frame, WorldInfo } from './world';

const info: WorldInfo = { width: 8, height: 6, tickHz: 20, maxSpeed: 1.3,
  nests: [{ colony: 0, x: -2.2, y: -1.1, radius: 0.9 }], midden: 0, tree: null };

export function petWorld(container: HTMLElement, getCare: () => Care | null, stroke: () => void) {
  const stage = createStage(container, new URLSearchParams(location.search).has('lite'));
  stage.setWorld(info);
  stage.over({ x: 0, y: 0 }, 0.78, Infinity);
  const view = new WorldView(stage.scene, info, true);
  const pet: CreatureState = { id: 0, colony: 0, x: 0, y: 0, heading: 1,
    speed: 0, size: 0.72, energy: 0.55, signal: -1, carrying: 0, holding: 0,
    nectar: 0, sprinting: 0, load: 0, young: 0.45, stamina: 1, dung: 0, z: 0 };
  let target = { x: 0, y: 0 }, until = 0, effectUntil = 0;
  let effect: CareAction | null = null, last = performance.now(), tick = 0, step = 0;
  let time = 0, running = true;
  const toy = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 12),
    new THREE.MeshStandardMaterial({ color: 0xe8b842, roughness: 0.6 }));
  toy.visible = false;
  stage.scene.add(toy);
  const hearts = new THREE.Group();
  for (let i = 0; i < 3; i++) {
    const shape = new THREE.Shape();
    shape.moveTo(0, 0);
    shape.bezierCurveTo(-0.4, 0.25, -0.2, 0.5, 0, 0.3);
    shape.bezierCurveTo(0.2, 0.5, 0.4, 0.25, 0, 0);
    const heart = new THREE.Mesh(new THREE.ShapeGeometry(shape),
      new THREE.MeshBasicMaterial({ color: 0xd86975, side: THREE.DoubleSide }));
    heart.position.x = (i - 1) * 0.4;
    hearts.add(heart);
  }
  stage.scene.add(hearts);
  let down: { x: number; y: number } | null = null;
  const ray = new THREE.Raycaster();
  const point = new THREE.Vector2();
  const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const hit = new THREE.Vector3();

  stage.renderer.domElement.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY }; });
  stage.renderer.domElement.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 8) return;
    down = null;
    const rect = container.getBoundingClientRect();
    point.set((e.clientX - rect.left) / rect.width * 2 - 1, -(e.clientY - rect.top) / rect.height * 2 + 1);
    ray.setFromCamera(point, stage.camera);
    const screenPet = new THREE.Vector3(pet.x, 0.4, pet.y).project(stage.camera);
    const distance = Math.hypot((screenPet.x - point.x) * rect.width / 2, (screenPet.y - point.y) * rect.height / 2);
    if (distance < 65) stroke();
    else if (effect === 'play' && time < effectUntil && ray.ray.intersectPlane(ground, hit)) {
      target = { x: Math.max(-3, Math.min(3, hit.x)), y: Math.max(-2, Math.min(2, hit.z)) };
      toy.position.set(target.x, 0.2, target.y);
    }
  });

  function react(action: CareAction) {
    effect = action;
    effectUntil = time + (action === 'play' ? 18 : 4);
    if (action === 'feed') target = { x: 1.5, y: 0.3 };
    if (action === 'play') {
      target = { x: 2, y: -0.8 };
      toy.position.set(target.x, 0.2, target.y);
    }
    until = effectUntil;
  }

  function frame(dt: number): Frame {
    const c = getCare();
    const active = time < effectUntil;
    toy.visible = !!c && active && effect === 'play';
    hearts.visible = !!c && !c.dead && active && (effect === 'stroke' || effect === 'clean' || effect === 'medicine');
    hearts.position.set(pet.x, 1.15 + Math.sin(time * 2) * 0.1, pet.y);
    hearts.quaternion.copy(stage.camera.quaternion);
    if (time > until) {
      target = { x: Math.sin(time * 1.7) * 2.4, y: Math.cos(time * 1.1) * 1.6 };
      until = time + 3 + Math.random() * 5;
    }
    const dx = target.x - pet.x, dy = target.y - pet.y, distance = Math.hypot(dx, dy);
    const resting = !c || c.dead || c.sick || isAsleep(c, c.updated);
    const speed = !resting && distance > 0.25 ? (toy.visible ? 1.2 : 0.45) : 0;
    if (speed) {
      pet.heading = Math.atan2(dy, dx);
      pet.x += dx / distance * Math.min(distance, speed * dt);
      pet.y += dy / distance * Math.min(distance, speed * dt);
    }
    if (toy.visible) {
      toy.position.y = 0.2 + Math.abs(Math.sin(time * 3)) * 0.25;
      if (distance < 0.35) {
        target = { x: Math.sin(time * 1.3) * 2.5, y: Math.cos(time * 1.9) * 1.6 };
        toy.position.x = target.x; toy.position.z = target.y;
      }
    }
    pet.speed = speed;
    pet.energy = c ? Math.max(0.05, c.fullness / 100) : 1;
    pet.z = active && effect === 'stroke' ? Math.max(0, Math.sin(time * 7)) * 0.14 : 0;
    pet.signal = active && effect === 'feed' && distance < 0.4 ? 0 : -1;
    return { tick: tick++, creatures: c && !c.dead ? [{ ...pet }] : [],
      food: active && effect === 'feed' && distance > 0.4 ? [{ id: 1, kind: 'common', x: 1.5, y: 0.3, z: 0, hidden: false }] : [],
      dung: c?.mess ?? [], blocks: [], stores: [], light: 1, eggs: [], flowers: [], flags: [] };
  }

  function render(now: number) {
    if (!running) return;
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now; time += dt; step += dt;
    if (step >= 0.05) { view.push(frame(step)); step = 0; }
    view.render(1, dt, time);
    stage.render(time);
    requestAnimationFrame(render);
  }
  requestAnimationFrame(render);
  return { react, home: () => { stage.release(); stage.over({ x: 0, y: 0 }, 0.78, Infinity); },
    stop: () => { running = false; view.dispose(); toy.geometry.dispose(); } };
}
