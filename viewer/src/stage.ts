// Renderer, camera (orbit, follow, the action camera, the &intro flyby), sky light, haze and bloom; the
// garden (garden.ts) is rebuilt for each world layout.

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { createLogger } from './lib/logger';
import { buildGarden, domeRadius, WALL } from './garden';
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
// the action camera (aim): how quickly it turns and zooms to a shot, how far it lets the shot's angle wander before
// turning to it, how far to one side of straight behind it looks from, and how long it leaves the view alone after
// someone moves it by hand
const AIM_RATE = 1.2;
const AIM_SLACK = 0.6;
const AIM_SIDE = 0.35;
const HANDS_OFF_MS = 8000;
// it looks down more steeply than the close-up, so who's behind a block reads at a glance, and pulls back to fit the
// shot's subjects (about their distance apart, with a margin) between these
const AIM_TILT = 0.9;
const AIM_NEAR = 9;
const AIM_FAR = 15;
// and it stays this far inside the glass dome, so the dome's frame never cuts across the view
const AIM_INSIDE = 1.5;

// lite (&lite) draws for a cool laptop: one pixel per point, no antialiasing, shadows or bloom
// turn (radians) swings the close-up round the blob it follows, so a reel can see a face coming its way
export function createStage(container: HTMLElement, lite = false, turn = 0) {
  const closeUp = CLOSE_UP.clone().applyAxisAngle(UP, turn);
  const renderer = new THREE.WebGLRenderer({ antialias: !lite });
  renderer.setPixelRatio(lite ? 1 : Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.shadowMap.enabled = !lite;
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
  let handsOff = 0;
  let aimYaw: number | null = null;
  controls.addEventListener('start', () => { handsOff = performance.now() + HANDS_OFF_MS; });

  const ambient = new THREE.HemisphereLight(GARDEN.skyLight, GARDEN.groundLight, 1.45);
  scene.add(ambient);
  // day and night: everything that lights the scene, at full day, and the same at full night
  const day = { sky: new THREE.Color(GARDEN.sky), skyLight: new THREE.Color(GARDEN.skyLight), ground: new THREE.Color(GARDEN.groundLight) };
  const night = { sky: new THREE.Color(GARDEN.nightSky), skyLight: new THREE.Color(GARDEN.nightSkyLight), ground: new THREE.Color(GARDEN.nightGroundLight) };
  let sun: THREE.DirectionalLight | null = null;
  let shown = -1;
  // everything that depends on the world's layout, rebuilt when a different one opens
  let garden: ReturnType<typeof buildGarden> | null = null;
  let dome = Infinity;

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  if (!lite) composer.addPass(new UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 0.35, 0.5, 0.92));
  composer.addPass(new OutputPass());

  function inside(x: number, y: number, z: number) {
    return Math.hypot(x, Math.max(0, y - WALL), z) < dome;
  }

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
    // in a game the left button walks you somewhere, so looking around moves to the right one
    lookWithRight() {
      controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
    },
    setWorld(info: WorldInfo) {
      if (garden) {
        scene.remove(garden.group);
        disposeAll(garden.group);
      }
      garden = buildGarden(info);
      dome = domeRadius(info) - AIM_INSIDE;
      scene.add(garden.group);
      sun = null;
      garden.group.traverse((o) => { if (o instanceof THREE.DirectionalLight) sun = o; });
      shown = -1;
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
      offset.subVectors(camera.position, controls.target).lerp(close ? closeUp : OVERVIEW, 1 - Math.exp(-dt * SWING_RATE));
      camera.position.addVectors(controls.target, offset);
    },
    // the action camera: slides to the shot, then turns to look from behind the one acting and pulls back to fit what
    // it's after, unless someone has just moved the view by hand
    aim(shot: { x: number; y: number; spread: number; from: number | null }, dt: number) {
      drifting = false;
      swinging = 0;
      const k = Number.isFinite(dt) ? 1 - Math.exp(-dt * FOLLOW_RATE) : 1;
      const dx = (shot.x - controls.target.x) * k;
      const dz = (shot.y - controls.target.z) * k;
      controls.target.x += dx;
      controls.target.z += dz;
      camera.position.x += dx;
      camera.position.z += dz;
      if (performance.now() < handsOff) return;
      offset.subVectors(camera.position, controls.target);
      const yaw = Math.atan2(offset.z, offset.x);
      const tilt = Math.atan2(offset.y, Math.hypot(offset.x, offset.z));
      const length = offset.length();
      if (shot.from !== null) {
        const want = shot.from + Math.PI + AIM_SIDE;
        if (aimYaw === null || Math.abs(wrap(want - aimYaw)) > AIM_SLACK) aimYaw = want;
      }
      const t = Number.isFinite(dt) ? 1 - Math.exp(-dt * AIM_RATE) : 1;
      const nextYaw = yaw + wrap((aimYaw ?? yaw) - yaw) * t;
      const nextTilt = tilt + (AIM_TILT - tilt) * t;
      const want = Math.min(AIM_FAR, Math.max(AIM_NEAR, shot.spread + 6));
      const nextLength = length + (want - length) * t;
      offset.set(Math.cos(nextYaw) * Math.cos(nextTilt), Math.sin(nextTilt), Math.sin(nextYaw) * Math.cos(nextTilt)).multiplyScalar(nextLength);
      // near the edge, closer in rather than out through the glass
      let scale = 1;
      while (scale > 0.4 && !inside(controls.target.x + offset.x * scale, offset.y * scale, controls.target.z + offset.z * scale)) scale -= 0.05;
      camera.position.copy(controls.target).addScaledVector(offset, scale);
    },
    // 1 by day, 0 at night
    light(level: number) {
      if (Math.abs(level - shown) < 0.005) return;
      shown = level;
      (scene.background as THREE.Color).lerpColors(night.sky, day.sky, level);
      (scene.fog as THREE.Fog).color.copy(scene.background as THREE.Color);
      ambient.color.lerpColors(night.skyLight, day.skyLight, level);
      ambient.groundColor.lerpColors(night.ground, day.ground, level);
      ambient.intensity = 0.55 + 0.9 * level;
      if (sun) (sun as THREE.DirectionalLight).intensity = 2.7 * level;
      renderer.toneMappingExposure = 1.08 * (0.75 + 0.25 * level);
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
    // time in seconds, for the grass; the nest domes fade by the camera
    render(time: number) {
      garden?.tick(time, camera);
      controls.update();
      composer.render();
    },
  };
}

function wrap(a: number) {
  return ((a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
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
