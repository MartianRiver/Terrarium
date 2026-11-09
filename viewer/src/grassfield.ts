// The grass ([grass], a replay's info.grass and each second's frame.grass): the lawn inside the hedge is bare ground and a
// soft green lies over it, as thick as the cover there, so grazing thins it and regrowth fills it back. One texel a cell,
// stretched smoothly over the arena, a hair above the lawn and under everything else.

import * as THREE from 'three';
import { GARDEN } from './palette';
import type { GrassInfo, WorldInfo } from './world';

const HEIGHT = 0.006;
// the most it hides the ground: a full cell still shows a little of the flecks under it
const DENSITY = 0.92;

export function addGrassField(scene: THREE.Object3D, info: WorldInfo, grid: GrassInfo) {
  const { n, cell } = grid;
  const green = new THREE.Color(GARDEN.meadow);
  const data = new Uint8Array(n * n * 4);
  for (let i = 0; i < n * n; i++) data.set([Math.round(green.r * 255), Math.round(green.g * 255), Math.round(green.b * 255), 0], i * 4);
  const texture = new THREE.DataTexture(data, n, n, THREE.RGBAFormat);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = texture.minFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
  // the grid starts at the arena's corner and may run a part-cell past the far one
  const size = n * cell;
  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(size, size).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ map: texture, transparent: true, roughness: 0.85, depthWrite: false }),
  );
  plane.position.set(-info.width / 2 + size / 2, HEIGHT, -info.height / 2 + size / 2);
  plane.receiveShadow = true;
  // nothing to show until the first cover arrives
  plane.visible = false;
  scene.add(plane);

  let shown: string | undefined;
  return (cover: string) => {
    if (cover === shown) return;
    shown = cover;
    if (!paint(data, cover, n)) return;
    texture.needsUpdate = true;
    plane.visible = true;
  };
}

// a frame's cover into the texture's alpha, false if it isn't the grid's size. The plane's top edge is the arena's far
// side (sim y up the grid is world z down the texture), so texture row j holds the cells with iy = n - 1 - j
export function paint(data: Uint8Array, cover: string, n: number, density = DENSITY): boolean {
  const bytes = atob(cover);
  if (bytes.length !== n * n) return false;
  for (let ix = 0; ix < n; ix++) {
    for (let iy = 0; iy < n; iy++) data[((n - 1 - iy) * n + ix) * 4 + 3] = Math.round(bytes.charCodeAt(ix * n + iy) * density);
  }
  return true;
}
