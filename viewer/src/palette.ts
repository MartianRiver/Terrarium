import { Color } from 'three';
import { SIGNAL_COUNT } from './world';

// Colony tints are soft and matte; signals are saturated and glow. The two sets
// must never overlap, otherwise a signal could pass for a colony colour.
export const COLONY_COLOURS = [0xf08a6c, 0x6fb3d9, 0xb48ee0, 0x9ccc7a].map((c) => new Color(c));

// index 0 is what the demo flashes on eating
export const SIGNAL_COLOURS = [0xfff36b, 0x4dffb8, 0xff4fa3, 0x58e6ff, 0xffffff].map((c) => new Color(c));
// an unlit bulb: a warm grey, away from the signals (though near enough to the white one that 0.4 should swap it for a hue)
export const SIGNAL_OFF_BULB = new Color(0x8c8279);

if (SIGNAL_COLOURS.length !== SIGNAL_COUNT) throw new Error('signal palette size does not match SIGNAL_COUNT');

// a garden under a glass dome on Mars, warm afternoon. Seasons will change these
export const GARDEN = {
  sky: 0xeabf96,
  skyLight: 0xfff0dc,
  groundLight: 0x9a6a4e,
  sun: 0xffdcb4,
  // the same at full night: a deep dusty blue, moonlit
  nightSky: 0x1e2340,
  nightSkyLight: 0x8fa2d8,
  nightGroundLight: 0x2a2236,
  // the plain outside the dome
  regolith: '#c46d40',
  regolithFlecks: ['#a9552f', '#d88a58', '#8e4628', '#e3a372'],
  rocks: [0x9e4c2c, 0xb8603a, 0x82402a, 0xc77a4c],
  mesa: 0xb5683f,
  glass: 0xe4f4ff,
  frame: 0xf3ede4,
  curb: 0xd8cbb8,
  // the bed under the dome, then the mown lawn inside the hedge and its stripes
  grass: '#93c26a',
  grassFlecks: ['#7fb35f', '#9ccb78', '#6fa452', '#a9d184'],
  lawn: '#bddb93',
  lawnStripe: '#b3d58a',
  lawnFlecks: ['#c8e6a8', '#b2d892'],
  blades: [0x8cc56f, 0x9fd17d, 0x7cb862],
  hedge: 0x74b062,
  leaves: [0x8cc56f, 0x6fb35d, 0xa8d27a],
  bark: 0xb08860,
  pebbles: [0xe8d9c4, 0xd9c8b0, 0xf0e4d2],
  petals: [0xffffff, 0xffd166, 0xff9fb2, 0xc9b6ff, 0xff8f6b],
  soil: 0xc9a37a,
  hole: 0x4a3524,
};
