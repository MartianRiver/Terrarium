// Renderer, camera (orbit, follow, the &intro flyby), sky light, haze and bloom; the
// garden (garden.ts) is rebuilt for each world layout.

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { createLogger } from './lib/logger';
import { buildGarden } from './garden';
import { GARDEN } from './palette';
import type { WorldInfo } from './world';

const log = createLogger('stage');

const OVERVIEW = new THREE.Vector3(0, 22, 26);
// where the camera sits from the blob it follows, and how quickly it catches up (per second)
const CLOSE_UP = new THREE.Vector3(0, 7, 9);
const FOLLOW_RATE = 3;
// switching between overview and close-up swings the camera over this long
const SWING_SECONDS = 2;
const SWING_RATE = 3;
// &intro: low outside the dome, circling slowly until the first F swoops down to the blob.
// Only turning (no closing in), so a replay seeked far ahead still starts outside
const INTRO = new THREE.Vector3(16, 15, 47);
const DRIFT_TURN = 0.05;
const UP = new THREE.Vector3(0, 1, 0);

export function createStage(container: HTMLElement) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(GARDEN.sky);
  // dusty haze; the mesas (55–75 m out) show as silhouettes in it
  scene.fog = new THREE.Fog(GARDEN.sky, 40, 115);

  const camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, 0.1, 200);
  camera.position.copy(OVERVIEW);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI / 2 - 0.12;
  controls.minDistance = 4;
  controls.maxDistance = 60;
  controls.target.set(0, 0, 0);
  let close = false;
  let swinging = 0;
  let drifting = false;
  const offset = new THREE.Vector3();

  scene.add(new THREE.HemisphereLight(GARDEN.skyLight, GARDEN.groundLight, 1.45));
  // everything that depends on the world's layout, rebuilt when a different one opens
  let garden: ReturnType<typeof buildGarden> | null = null;

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 0.35, 0.5, 0.92);
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
    setWorld(info: WorldInfo) {
      if (garden) {
        scene.remove(garden.group);
        disposeAll(garden.group);
      }
      garden = buildGarden(info);
      scene.add(garden.group);
      log.debug('world built', { width: info.width, height: info.height, nests: info.nests.length });
    },
    // slides the orbit after the blob (or back to the middle with null), keeping whatever angle and
    // zoom it has, except while swinging between views; dt Infinity jumps straight there
    track(at: { x: number; y: number } | null, dt: number) {
      if (drifting && Number.isFinite(dt)) {
        offset.subVectors(camera.position, controls.target).applyAxisAngle(UP, dt * DRIFT_TURN);
        camera.position.addVectors(controls.target, offset);
      }
      if (!at && swinging <= 0) return;
      const goal = at ?? { x: 0, y: 0 };
      const k = 1 - Math.exp(-dt * FOLLOW_RATE);
      const dx = (goal.x - controls.target.x) * k;
      const dz = (goal.y - controls.target.z) * k;
      controls.target.x += dx;
      controls.target.z += dz;
      camera.position.x += dx;
      camera.position.z += dz;
      if (swinging <= 0) return;
      swinging -= dt;
      offset.subVectors(camera.position, controls.target).lerp(close ? CLOSE_UP : OVERVIEW, 1 - Math.exp(-dt * SWING_RATE));
      camera.position.addVectors(controls.target, offset);
    },
    view(closeUp: boolean) {
      drifting = false;
      close = closeUp;
      swinging = SWING_SECONDS;
    },
    intro() {
      camera.position.copy(INTRO);
      drifting = true;
    },
    // time in seconds, for the grass
    render(time: number) {
      garden?.tick(time);
      controls.update();
      composer.render();
    },
  };
}

function disposeAll(root: THREE.Object3D) {
  root.traverse((o) => {
    if (o instanceof THREE.DirectionalLight) o.shadow.dispose();
    if (o instanceof THREE.InstancedMesh) o.dispose();
    if (!(o instanceof THREE.Mesh)) return;
    o.geometry.dispose();
    for (const m of [o.material].flat()) {
      for (const v of Object.values(m)) if (v instanceof THREE.Texture) v.dispose();
      m.dispose();
    }
  });
}
