// The contract between whatever produces the world (the stage 0 demo now, sim
// replays later) and the renderer. Sim space is a flat ground plane: x/y in
// metres, heading in radians with 0 = +x, counter-clockwise.

export const SIGNAL_COUNT = 5;
export const SIGNAL_OFF = -1;

// jelly is what a Terrikin leaves when it unloads its crop outside a nest (0.3 on)
export type FoodKind = 'common' | 'rich' | 'jelly';

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
  carrying: number; // food eaten past full, held in its crop to make jelly; 0 in replays from before 0.3
  holding: number; // 1 while it grips a block (grab); 0 in replays of worlds without grab
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

// jelly in a colony's store, in food unloaded
export interface StoreState {
  colony: number;
  jelly: number;
}

// an egg on its colony's nest; the Terrikin that hatches from it takes its id (worlds with hatching)
export interface EggState {
  id: number;
  colony: number;
  x: number;
  y: number;
  progress: number; // 0 when laid, 1 as it hatches
}

export interface Frame {
  tick: number;
  creatures: CreatureState[];
  food: FoodState[];
  blocks: BlockState[];
  stores: StoreState[]; // empty in replays from before 0.3
  light: number; // 1 by day, 0 at night; always 1 in worlds without nights
  eggs: EggState[]; // empty in worlds without hatching and replays from before it
}
