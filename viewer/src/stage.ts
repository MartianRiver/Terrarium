// Renderer, camera, lights, ground and decoration. Decoration is seeded and
// purely visual: the sim never sees rocks or grass placed here.

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { createLogger } from './lib/logger';
import { COLONY_COLOURS, GROUND, SKY } from './palette';
import type { NestInfo, WorldInfo } from './world';

const log = createLogger('stage');

function seeded(seed: number) {
  return () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

export function createStage(container: HTMLElement, info: WorldInfo) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SKY);
  scene.fog = new THREE.Fog(SKY, 40, 90);

  const camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, 0.1, 200);
  camera.position.set(0, 22, 26);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI / 2 - 0.12;
  controls.minDistance = 4;
  controls.maxDistance = 60;
  controls.target.set(0, 0, 0);

  addLights(scene, info);
  addGround(scene, info);
  for (const nest of info.nests) addNest(scene, nest);
  addDecor(scene, info);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 0.55, 0.5, 0.9);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    composer.setSize(w, h);
  }
  window.addEventListener('resize', resize);

  log.info('stage ready', { size: [container.clientWidth, container.clientHeight], pixelRatio: renderer.getPixelRatio() });

  return {
    renderer, scene, camera,
    render() {
      controls.update();
      composer.render();
    },
  };
}

function addLights(scene: THREE.Scene, info: WorldInfo) {
  scene.add(new THREE.HemisphereLight(0xdff2ff, 0x6b7f4a, 1.4));
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
  sun.position.set(12, 24, 8);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const r = Math.max(info.width, info.height) * 0.75;
  Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 1, far: 70 });
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.03;
  sun.shadow.radius = 4;
  scene.add(sun);
}

function addGround(scene: THREE.Scene, info: WorldInfo) {
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(80, 64).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: GROUND, roughness: 1 }),
  );
  ground.receiveShadow = true;
  scene.add(ground);

  // slightly lighter play area so the bounds read clearly
  const arena = new THREE.Mesh(
    new THREE.PlaneGeometry(info.width, info.height).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: new THREE.Color(GROUND).offsetHSL(0.01, 0.02, 0.05), roughness: 1 }),
  );
  arena.position.y = 0.005;
  arena.receiveShadow = true;
  scene.add(arena);

  // low rounded walls on the boundary
  const wallMat = new THREE.MeshStandardMaterial({ color: 0xc9b99a, roughness: 0.9 });
  const t = 0.5, h = 0.6;
  const sides: [number, number, number, number][] = [
    [0, -info.height / 2 - t / 2, info.width + t * 2, t],
    [0, info.height / 2 + t / 2, info.width + t * 2, t],
    [-info.width / 2 - t / 2, 0, t, info.height],
    [info.width / 2 + t / 2, 0, t, info.height],
  ];
  for (const [x, z, w, d] of sides) {
    const wall = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, 0.15), wallMat);
    wall.position.set(x, h / 2, z);
    wall.castShadow = true;
    wall.receiveShadow = true;
    scene.add(wall);
  }
}

function addNest(scene: THREE.Scene, nest: NestInfo) {
  const tint = COLONY_COLOURS[nest.colony % COLONY_COLOURS.length];
  const mound = new THREE.Mesh(
    new THREE.SphereGeometry(nest.radius, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.32, 1),
    new THREE.MeshStandardMaterial({ color: 0xa88a64, roughness: 1 }),
  );
  mound.position.set(nest.x, 0, nest.y);
  mound.castShadow = true;
  mound.receiveShadow = true;
  scene.add(mound);

  const hole = new THREE.Mesh(new THREE.CircleGeometry(nest.radius * 0.28, 24).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: 0x2b2018 }));
  hole.position.set(nest.x, nest.radius * 0.32 + 0.01, nest.y);
  scene.add(hole);

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(nest.radius * 1.05, nest.radius * 1.25, 48).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: tint, roughness: 0.8 }),
  );
  ring.position.set(nest.x, 0.012, nest.y);
  ring.receiveShadow = true;
  scene.add(ring);
}

function addDecor(scene: THREE.Scene, info: WorldInfo) {
  const rng = seeded(42);
  const dummy = new THREE.Object3D();

  // grass tufts across arena and surroundings
  const tufts = 900;
  const grass = new THREE.InstancedMesh(
    new THREE.ConeGeometry(0.05, 0.3, 4).translate(0, 0.15, 0),
    new THREE.MeshStandardMaterial({ color: 0x6f9f4b, roughness: 1 }),
    tufts,
  );
  const spread = Math.max(info.width, info.height) * 1.6;
  for (let i = 0; i < tufts; i++) {
    dummy.position.set((rng() - 0.5) * spread, 0, (rng() - 0.5) * spread);
    dummy.rotation.set((rng() - 0.5) * 0.4, rng() * Math.PI, (rng() - 0.5) * 0.4);
    dummy.scale.setScalar(0.6 + rng() * 0.9);
    dummy.updateMatrix();
    grass.setMatrixAt(i, dummy.matrix);
  }
  scene.add(grass);

  // rocks outside the walls only, so nothing looks like an obstacle the sim ignores
  const rocks = 40;
  const rock = new THREE.InstancedMesh(
    new THREE.DodecahedronGeometry(0.6, 0),
    new THREE.MeshStandardMaterial({ color: 0xa39c91, roughness: 0.95, flatShading: true }),
    rocks,
  );
  rock.castShadow = true;
  rock.receiveShadow = true;
  const hx = info.width / 2 + 1.5, hz = info.height / 2 + 1.5;
  for (let i = 0; i < rocks; i++) {
    let x = 0, z = 0;
    while (Math.abs(x) < hx && Math.abs(z) < hz) {
      x = (rng() - 0.5) * (hx * 2 + 20);
      z = (rng() - 0.5) * (hz * 2 + 20);
    }
    dummy.position.set(x, 0.1, z);
    dummy.rotation.set(rng() * 3, rng() * 3, rng() * 3);
    const s = 0.5 + rng() * 1.6;
    dummy.scale.set(s, s * (0.5 + rng() * 0.4), s);
    dummy.updateMatrix();
    rock.setMatrixAt(i, dummy.matrix);
  }
  scene.add(rock);
}
