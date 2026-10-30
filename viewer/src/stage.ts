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
const ORIGIN = new THREE.Vector3();
// the action camera (aim) moves on springs, so a tag or a new pair glides rather than jerks: how stiff its slide to
// the shot is, its turn and tilt, and its pull-back (out quickly, in slowly, so a chase doesn't breathe in and out)
const AIM_FOLLOW = 2.5;
const AIM_TURN = 1;
const AIM_OUT = 1.2;
const AIM_IN = 0.4;
// the shot's angle is smoothed over about this many seconds before the camera turns to it, and it looks from this far
// to one side of straight behind; it leaves the view alone this long after someone moves it by hand
const AIM_SETTLE = 2;
const AIM_SIDE = 0.35;
const HANDS_OFF_MS = 8000;
// it looks down more steeply than the close-up, so who's behind a block reads at a glance, and pulls back to fit the
// shot's subjects (about their distance apart, with a margin) between these
const AIM_TILT = 0.9;
const AIM_NEAR = 9;
const AIM_FAR = 15;
// and it stays this far inside the glass dome, so the dome's frame never cuts across the view
const AIM_INSIDE = 1.5;
// the wide shot: the whole arena, its long side across the screen, looking down this steeply, pulled back until every
// corner (and a margin for the hedges) fits inside this much of the screen; it eases there at WIDE_RATE
const WIDE_TILT = 0.72;
const WIDE_MARGIN = 0.8;
const WIDE_FIT = 0.92;
const WIDE_RATE = 2;

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
  // the action camera's speeds, and its smoothed angle (fx, fz) and arm: null until it aims, and again after a hand
  let rig: { vx: number; vz: number; fx: number; fz: number } | null = null;
  let arm: { yaw: number; tilt: number; length: number; vyaw: number; vtilt: number; vlength: number } | null = null;
  controls.addEventListener('start', () => { handsOff = performance.now() + HANDS_OFF_MS; });
  // the wide shot's place for this arena and screen shape, worked out again when either changes
  let arena = { width: 20, height: 20 };
  let widePos: THREE.Vector3 | null = null;
  const probe = new THREE.PerspectiveCamera();
  const corner = new THREE.Vector3();

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

  // how far the camera can sit from the target along (ux, uy, uz) and stay inside the dome
  function room(ux: number, uy: number, uz: number) {
    const { x, z } = controls.target;
    if (inside(x + ux * AIM_FAR, uy * AIM_FAR, z + uz * AIM_FAR)) return AIM_FAR;
    let lo = 0, hi = AIM_FAR;
    for (let i = 0; i < 12; i++) {
      const mid = (lo + hi) / 2;
      if (inside(x + ux * mid, uy * mid, z + uz * mid)) lo = mid;
      else hi = mid;
    }
    return lo;
  }

  function fitWide() {
    const hx = arena.width / 2 + WIDE_MARGIN, hz = arena.height / 2 + WIDE_MARGIN;
    // camera on the +z side puts the arena's width across the screen, on the +x side its height
    const yaw = (arena.width >= arena.height) === (camera.aspect >= 1) ? Math.PI / 2 : 0;
    const dir = new THREE.Vector3(Math.cos(yaw) * Math.cos(WIDE_TILT), Math.sin(WIDE_TILT), Math.sin(yaw) * Math.cos(WIDE_TILT));
    probe.copy(camera);
    const fits = (d: number) => {
      probe.position.copy(dir).multiplyScalar(d);
      probe.lookAt(0, 0, 0);
      probe.updateMatrixWorld();
      for (const x of [-hx, hx]) for (const y of [0, WALL]) for (const z of [-hz, hz]) {
        corner.set(x, y, z).project(probe);
        if (Math.abs(corner.x) > WIDE_FIT || Math.abs(corner.y) > WIDE_FIT) return false;
      }
      return true;
    };
    let lo = 4, hi = 150;
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      if (fits(mid)) hi = mid;
      else lo = mid;
    }
    return dir.multiplyScalar(hi);
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    widePos = null;
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
      arena = { width: info.width, height: info.height };
      widePos = null;
      scene.add(garden.group);
      sun = null;
      garden.group.traverse((o) => { if (o instanceof THREE.DirectionalLight) sun = o; });
      shown = -1;
      log.debug('world built', { width: info.width, height: info.height, nests: info.nests.length });
    },
    // slides the orbit after the blob (or back to the middle with null), keeping whatever angle and
    // zoom it has, except while swinging between views; dt Infinity jumps straight there
    track(at: { x: number; y: number } | null, dt: number) {
      rig = arm = null;
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
      if (swinging > 0) {
        swinging -= dt;
        offset.subVectors(camera.position, controls.target).lerp(close ? closeUp : OVERVIEW, 1 - Math.exp(-dt * SWING_RATE));
        camera.position.addVectors(controls.target, offset);
      }
      // close behind a Terrikin by the edge, closer in rather than out through the glass
      if (!at || !close) return;
      offset.subVectors(camera.position, controls.target);
      const length = offset.length();
      offset.divideScalar(length);
      const most = Math.max(3.5, room(offset.x, offset.y, offset.z));
      if (length > most) camera.position.copy(controls.target).addScaledVector(offset, most);
    },
    // the action camera: glides to the shot, then turns to look from behind the one acting and pulls back to fit what
    // it's after, unless someone has just moved the view by hand
    aim(shot: { x: number; y: number; spread: number; from: number | null }, dt: number) {
      drifting = false;
      swinging = 0;
      const snap = !Number.isFinite(dt);
      if (snap || !rig) rig = { vx: 0, vz: 0, fx: 0, fz: 0 };
      if (snap) arm = null;
      const t = controls.target;
      let x, z;
      if (snap) [x, z] = [shot.x, shot.y];
      else {
        [x, rig.vx] = spring(t.x, rig.vx, shot.x, AIM_FOLLOW, dt);
        [z, rig.vz] = spring(t.z, rig.vz, shot.y, AIM_FOLLOW, dt);
      }
      camera.position.x += x - t.x;
      camera.position.z += z - t.z;
      t.x = x;
      t.z = z;
      if (shot.from !== null) {
        const k = snap ? 1 : 1 - Math.exp(-dt / AIM_SETTLE);
        rig.fx += (Math.cos(shot.from) - rig.fx) * k;
        rig.fz += (Math.sin(shot.from) - rig.fz) * k;
      }
      if (performance.now() < handsOff) {
        arm = null;
        return;
      }
      if (!arm) {
        offset.subVectors(camera.position, t);
        arm = { yaw: Math.atan2(offset.z, offset.x), tilt: Math.atan2(offset.y, Math.hypot(offset.x, offset.z)),
                length: offset.length(), vyaw: 0, vtilt: 0, vlength: 0 };
      }
      // the smoothed angle is too short to trust when the shot keeps changing its mind, so then the camera holds still
      const yaw = Math.hypot(rig.fx, rig.fz) > 0.3 ? Math.atan2(rig.fz, rig.fx) + Math.PI + AIM_SIDE : arm.yaw;
      const want = Math.min(AIM_FAR, Math.max(AIM_NEAR, shot.spread + 6));
      if (snap) Object.assign(arm, { yaw, tilt: AIM_TILT, length: want });
      else {
        [arm.yaw, arm.vyaw] = spring(arm.yaw, arm.vyaw, arm.yaw + wrap(yaw - arm.yaw), AIM_TURN, dt);
        [arm.tilt, arm.vtilt] = spring(arm.tilt, arm.vtilt, AIM_TILT, AIM_TURN, dt);
        [arm.length, arm.vlength] = spring(arm.length, arm.vlength, want, want > arm.length ? AIM_OUT : AIM_IN, dt);
      }
      offset.set(Math.cos(arm.yaw) * Math.cos(arm.tilt), Math.sin(arm.tilt), Math.sin(arm.yaw) * Math.cos(arm.tilt));
      // near the edge, closer in rather than out through the glass
      const most = Math.max(3.5, room(offset.x, offset.y, offset.z));
      if (arm.length > most) {
        arm.length = most;
        arm.vlength = Math.min(0, arm.vlength);
      }
      camera.position.copy(t).addScaledVector(offset, arm.length);
    },
    // the wide shot: eases to the whole arena on screen, unless someone has just moved the view by hand
    wide(dt: number) {
      drifting = false;
      swinging = 0;
      rig = arm = null;
      if (performance.now() < handsOff) return;
      widePos ??= fitWide();
      const k = Number.isFinite(dt) ? 1 - Math.exp(-dt * WIDE_RATE) : 1;
      controls.target.lerp(ORIGIN, k);
      camera.position.lerp(widePos, k);
    },
    // a new camera mode takes over at once, whoever last touched the view
    release() {
      handsOff = 0;
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

// a critically damped spring from x (speed v) towards goal after dt seconds, exact for any dt; stiffness w per second
function spring(x: number, v: number, goal: number, w: number, dt: number): [number, number] {
  const e = x - goal, c = v + w * e, d = Math.exp(-w * dt);
  return [goal + (e + c * dt) * d, (v - w * c * dt) * d];
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
