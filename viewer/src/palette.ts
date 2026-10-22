import { Color } from 'three';
import { SIGNAL_COUNT } from './world';

// Colony tints are soft and matte; signals are saturated and glow. The two sets
// must never overlap, otherwise a signal could pass for a colony colour.
export const COLONY_COLOURS = [0xf08a6c, 0x6fb3d9, 0xb48ee0, 0x9ccc7a].map((c) => new Color(c));

// index 0 is what the demo flashes on eating
export const SIGNAL_COLOURS = [0xfff36b, 0x4dffb8, 0xff4fa3, 0x58e6ff, 0xffffff].map((c) => new Color(c));
export const SIGNAL_DARK = new Color(0x3a3a46);

if (SIGNAL_COLOURS.length !== SIGNAL_COUNT) throw new Error('signal palette size does not match SIGNAL_COUNT');

export const GROUND = 0x9fc27a;
export const SKY = 0xcfe8f2;
