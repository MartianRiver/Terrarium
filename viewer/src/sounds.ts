// The world's sounds in the browser, mixed the way reel/sound.py mixes a reel: a sound for each cue that's on screen
// (4 dB down from the overview), wind all the time, birds by day and crickets by night from the light, and music
// under it, dipped at night. Off until asked for, since browsers only start audio after a click or a key.

import * as THREE from 'three';
import type { Cue, CueKind } from './cues';
import { createLogger } from './lib/logger';

const log = createLogger('sounds');

interface Voice {
  files: string[];
  db: number;
  rate?: [number, number];
  lowpass?: number;
}

// reel/sound.json's nursery profile, with the colony sounds it leaves out from the garden one
const WORLD: Record<CueKind, Voice> = {
  bite: { files: ['bite-1', 'bite-2'], db: -30, rate: [0.85, 1.0], lowpass: 3500 },
  found: { files: ['found'], db: -27, rate: [1.0, 1.1], lowpass: 8000 },
  tag: { files: ['tag'], db: -30, rate: [1.0, 1.15], lowpass: 7000 },
  sprint: { files: ['sprint'], db: -38, rate: [1.1, 1.3], lowpass: 5000 },
  hatch: { files: ['hatch'], db: -30, rate: [0.85, 0.95], lowpass: 3000 },
  nectar: { files: ['nectar'], db: -35, lowpass: 6000 },
  unload: { files: ['unload'], db: -29, rate: [0.55, 0.65], lowpass: 2500 },
  death: { files: ['death-1', 'death-2'], db: -26, rate: [0.75, 0.85], lowpass: 2500 },
};
const BEDS: { file: string; db: number; lowpass: number; when: 'always' | 'day' | 'night' }[] = [
  { file: 'wind', db: -40, lowpass: 3000, when: 'always' },
  { file: 'birds', db: -38, lowpass: 6000, when: 'day' },
  { file: 'crickets', db: -33, lowpass: 3500, when: 'night' },
];
const MUSIC = { file: 'music', db: -13, nightDip: 0.85 };
// a reel is loudness-normalised to -14 LUFS after mixing, which lifts these levels by about this much
const MASTER_DB = 10;
const XFADE = 2; // seconds over a loop's seam
// camera distances (m) of the close-up and the overview: sound.py plays the overview 4 dB down
const CLOSE = 12;
const FAR = 34;
// of one kind at once, or a busy colony is a hailstorm of bites
const MAX_VOICES = 3;
const KEY = 'terrarium.sound';

const db = (d: number) => 10 ** (d / 20);

interface Clip {
  buffer: AudioBuffer;
  gain: number; // to its peak, as sound.py's decode does
  start: number; // seconds of silence it leads with, skipped (it reads as lag)
}

function prepare(buffer: AudioBuffer): Clip {
  let peak = 1e-6;
  for (let c = 0; c < buffer.numberOfChannels; c++) for (const x of buffer.getChannelData(c)) peak = Math.max(peak, Math.abs(x));
  let first = buffer.length;
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const i = buffer.getChannelData(c).findIndex((x) => Math.abs(x) / peak > 0.05);
    if (i >= 0) first = Math.min(first, i);
  }
  return { buffer, gain: 1 / peak, start: Math.max(0, first - buffer.sampleRate / 200) / buffer.sampleRate };
}

// the loop's tail faded into its head, so the seam doesn't click or jump (sound.py's bed())
function seamless(ctx: BaseAudioContext, a: AudioBuffer): AudioBuffer {
  const x = Math.min(Math.floor(XFADE * a.sampleRate), Math.floor(a.length / 2));
  const n = a.length - x;
  const out = ctx.createBuffer(a.numberOfChannels, n, a.sampleRate);
  for (let c = 0; c < a.numberOfChannels; c++) {
    const src = a.getChannelData(c);
    const dst = out.getChannelData(c);
    dst.set(src.subarray(0, n));
    for (let i = 0; i < x; i++) dst[i] = src[i] * (i / x) + src[n + i] * (1 - i / x);
  }
  return out;
}

function saved(): { on: boolean; music: boolean } {
  try {
    return { on: false, music: true, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') };
  } catch {
    return { on: false, music: true };
  }
}

export class Sounds {
  readonly button = document.createElement('button');
  readonly musicButton = document.createElement('button');
  private state: 'off' | 'loading' | 'on' | 'error' = 'off';
  private ctx: AudioContext | null = null;
  private clips = new Map<string, Clip>();
  private loaded = false;
  private fx!: GainNode;
  private beds: { when: string; level: number; gain: GainNode }[] = [];
  private musicGain!: GainNode;
  private music = true;
  private night = 0;
  private playing = new Map<CueKind, number>();
  private at = new THREE.Vector3();
  private onScreen = new THREE.Vector3();

  constructor(private camera: THREE.Camera) {
    const prefs = saved();
    this.music = prefs.music;
    this.button.type = this.musicButton.type = 'button';
    this.button.addEventListener('click', () => void this.toggle());
    this.musicButton.addEventListener('click', () => this.setMusic(!this.music));
    this.show();
    // asked for last time: on again at the first click or key, the soonest a browser allows
    if (prefs.on) {
      const go = (e: Event) => {
        removeEventListener('pointerdown', go, true);
        removeEventListener('keydown', go, true);
        // the button and M turn it on themselves
        const own = e.target === this.button || (e instanceof KeyboardEvent && e.key.toLowerCase() === 'm');
        if (!own && this.state === 'off') void this.start();
      };
      addEventListener('pointerdown', go, true);
      addEventListener('keydown', go, true);
    }
    document.addEventListener('visibilitychange', () => {
      if (!this.ctx || this.state !== 'on') return;
      void (document.hidden ? this.ctx.suspend() : this.ctx.resume());
    });
  }

  async toggle() {
    if (this.state === 'loading') return;
    if (this.state === 'on') {
      this.state = 'off';
      await this.ctx?.suspend();
      this.save();
      this.show();
      log.info('sound off');
      return;
    }
    await this.start();
  }

  private async start() {
    this.state = 'loading';
    this.show();
    try {
      this.ctx ??= new AudioContext();
      await this.ctx.resume();
      if (!this.loaded) await this.load(this.ctx);
      this.state = 'on';
      this.light(this.night, true);
      log.info('sound on', { music: this.music });
    } catch (err) {
      this.state = 'error';
      log.error('sound failed to start', { err: String(err) });
    }
    this.save();
    this.show();
  }

  private async load(ctx: AudioContext) {
    const names = [...new Set([...Object.values(WORLD).flatMap((v) => v.files), ...BEDS.map((b) => b.file), MUSIC.file])];
    const base = import.meta.env.BASE_URL;
    await Promise.all(names.map(async (name) => {
      const res = await fetch(`${base}sounds/${name}.mp3`);
      if (!res.ok) throw new Error(`${name}.mp3: the server said ${res.status}`);
      this.clips.set(name, prepare(await ctx.decodeAudioData(await res.arrayBuffer())));
    }));
    const limit = ctx.createDynamicsCompressor();
    limit.threshold.value = -3;
    limit.knee.value = 0;
    limit.ratio.value = 20;
    limit.connect(ctx.destination);
    const master = ctx.createGain();
    master.gain.value = db(MASTER_DB);
    master.connect(limit);
    this.fx = ctx.createGain();
    this.fx.connect(master);
    for (const b of BEDS) this.beds.push({ when: b.when, level: db(b.db), gain: this.loop(ctx, b.file, master, b.lowpass) });
    this.musicGain = this.loop(ctx, MUSIC.file, master);
    this.loaded = true;
    log.info('sounds loaded', { files: names.length });
  }

  private loop(ctx: AudioContext, name: string, to: AudioNode, lowpass?: number): GainNode {
    const clip = this.clips.get(name)!;
    const src = ctx.createBufferSource();
    src.buffer = seamless(ctx, clip.buffer);
    src.loop = true;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const norm = ctx.createGain();
    norm.gain.value = clip.gain;
    let head: AudioNode = src;
    if (lowpass) {
      const lp = new BiquadFilterNode(ctx, { type: 'lowpass', frequency: lowpass });
      src.connect(lp);
      head = lp;
    }
    head.connect(norm).connect(gain).connect(to);
    src.start();
    return gain;
  }

  // light 1 by day, 0 at night, as the frames have it; dusk and dawn ease in over a second or so
  light(light: number, now = false) {
    const night = Math.min(1, Math.max(0, 1 - light * 1.6));
    if (!now && Math.abs(night - this.night) < 0.01) return;
    this.night = night;
    if (this.state !== 'on' || !this.ctx) return;
    const t = this.ctx.currentTime;
    const ease = now ? 0.05 : 0.6;
    for (const b of this.beds) {
      const share = b.when === 'night' ? night : b.when === 'day' ? 1 - night : 1;
      b.gain.gain.setTargetAtTime(b.level * share, t, ease);
    }
    const music = this.music ? db(MUSIC.db) * (1 - night * MUSIC.nightDip) : 0;
    this.musicGain.gain.setTargetAtTime(music, t, now ? 0.05 : ease);
  }

  hear(cues: Cue[]) {
    if (this.state !== 'on' || !this.ctx || document.hidden) return;
    for (const cue of cues) this.play(this.ctx, cue);
  }

  private play(ctx: AudioContext, cue: Cue) {
    const voice = WORLD[cue.kind];
    if ((this.playing.get(cue.kind) ?? 0) >= MAX_VOICES) return;
    this.at.set(cue.x, 0.3, cue.y);
    const p = this.onScreen.copy(this.at).project(this.camera);
    if (Math.abs(p.x) > 1.05 || Math.abs(p.y) > 1.05 || p.z > 1) return;
    const far = Math.min(1, Math.max(0, (this.camera.position.distanceTo(this.at) - CLOSE) / (FAR - CLOSE)));
    const clip = this.clips.get(voice.files[Math.floor(Math.random() * voice.files.length)])!;
    const [lo, hi] = voice.rate ?? [1, 1];
    const src = new AudioBufferSourceNode(ctx, { buffer: clip.buffer, playbackRate: lo + Math.random() * (hi - lo) });
    const gain = new GainNode(ctx, { gain: db(voice.db - 4 * far) * clip.gain });
    const pan = new StereoPannerNode(ctx, { pan: Math.max(-1, Math.min(1, p.x * 0.6)) });
    let head: AudioNode = src;
    if (voice.lowpass) head = src.connect(new BiquadFilterNode(ctx, { type: 'lowpass', frequency: voice.lowpass }));
    head.connect(gain).connect(pan).connect(this.fx);
    this.playing.set(cue.kind, (this.playing.get(cue.kind) ?? 0) + 1);
    src.onended = () => this.playing.set(cue.kind, (this.playing.get(cue.kind) ?? 1) - 1);
    src.start(0, clip.start);
  }

  private setMusic(on: boolean) {
    this.music = on;
    this.light(this.night, true);
    this.save();
    this.show();
    log.info(on ? 'music on' : 'music off');
  }

  private save() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ on: this.state === 'on', music: this.music }));
    } catch {
      // private windows can refuse; it just won't be remembered
    }
  }

  private show() {
    const b = this.button;
    const words = { off: 'Sound', loading: 'Sound…', on: 'Sound', error: 'No sound' }[this.state];
    b.textContent = words;
    b.disabled = this.state === 'loading';
    b.setAttribute('aria-pressed', String(this.state === 'on'));
    b.setAttribute('aria-label', {
      off: 'Sound is off. Turn it on',
      loading: 'Loading the sounds',
      on: 'Sound is on. Turn it off',
      error: 'The sounds didn’t load. Try again',
    }[this.state]);
    b.title = this.state === 'error' ? 'The sounds didn’t load. Click to try again.' : '';
    const m = this.musicButton;
    m.hidden = this.state !== 'on';
    m.textContent = '♪';
    m.setAttribute('aria-pressed', String(this.music));
    m.setAttribute('aria-label', this.music ? 'Music is on. Turn it off' : 'Music is off. Turn it on');
  }
}
