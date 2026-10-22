// The contract between whatever produces the world (the stage 0 demo now, sim
// replays later) and the renderer. Sim space is a flat ground plane: x/y in
// metres, heading in radians with 0 = +x, counter-clockwise.

export const SIGNAL_COUNT = 5;
export const SIGNAL_OFF = -1;

export type FoodKind = 'common' | 'rich';

export interface CreatureState {
  id: number;
  colony: number;
  x: number;
  y: number;
  heading: number;
  speed: number;
  size: number;
  energy: number; // 0..1
  signal: number; // SIGNAL_OFF or 0..SIGNAL_COUNT-1
}

export interface FoodState {
  id: number;
  kind: FoodKind;
  x: number;
  y: number;
}

export interface BlockState {
  id: number;
  x: number;
  y: number;
  angle: number;
  w: number;
  h: number;
}

export interface NestInfo {
  colony: number;
  x: number;
  y: number;
  radius: number;
}

// Static for the life of an episode
export interface WorldInfo {
  width: number;
  height: number;
  tickHz: number;
  maxSpeed: number;
  nests: NestInfo[];
}

export interface Frame {
  tick: number;
  creatures: CreatureState[];
  food: FoodState[];
  blocks: BlockState[];
}
