// Ties the brain window to what's playing: which run checkpoint the replay came from (only those have a brain to
// read, through the local runs server), which Terrikin is followed, loading its mind track once, and checking the
// replay is the episode the mind was played in.

import type * as THREE from 'three';
import { clock } from './clock';
import { createLogger } from './lib/logger';
import { MindPanel } from './mindpanel';
import { MindTrack, readMind } from './mindtrack';
import { NetView, type Wiring } from './netview';
import { type Pose, SightFan } from './sightfan';
import type { Frame } from './world';

const log = createLogger('brain');

export interface RunReplay {
  run: string;
  checkpoint: string;
  seed: number;
  here: boolean;
}

// /api/runs/<id>/replay/<checkpoint>?seed=N[&here]: a run's checkpoint, whose brain the server can read
export function runReplay(url: URL): RunReplay | null {
  const m = url.pathname.match(/^\/api\/runs\/([\w.-]+)\/replay\/([\w.-]+\.pt)$/);
  if (!m) return null;
  return { run: m[1], checkpoint: m[2], seed: Number(url.searchParams.get('seed') ?? 0), here: url.searchParams.has('here') };
}

export class BrainView {
  readonly panel: MindPanel;
  private playing: RunReplay | null = null;
  private frames: Frame[] = [];
  private minds = new Map<string, Promise<MindTrack>>();
  private track: MindTrack | null = null;
  private wanted: string | null = null;
  private fan: SightFan | null = null;
  private dead = false;
  private said = '';
  private net: NetView;
  private wirings = new Map<string, Promise<Wiring>>();
  // the name of each Terrikin in what's playing (names.ts)
  name: (id: number) => string = (id) => `Terrikin ${id}`;

  // again: open the same replay recorded on this machine
  constructor(parent: HTMLElement, private scene: THREE.Scene, private again: (url: URL) => void) {
    this.panel = new MindPanel(parent);
    this.panel.say('Brain', null);
    this.net = new NetView(parent);
    this.panel.wired = () => this.toggleNet();
  }

  // the wired-up view opens the brain window too, since that's what picks and loads the mind
  toggleNet() {
    this.net.toggle();
    if (this.net.open && !this.open) this.toggle();
  }

  get open() {
    return this.panel.open;
  }

  toggle() {
    this.panel.toggle();
    if (!this.open) {
      this.fan?.hide();
      this.net.toggle(false);
    }
  }

  // a replay opened: url is where it came from (null for a file), frames what it plays
  playingNow(url: URL | null, frames: Frame[]) {
    this.playing = url ? runReplay(url) : null;
    this.frames = frames;
    this.wanted = null;
  }

  // every drawn frame: the Terrikin followed, where it is and the tick
  frame(id: number | null, at: Pose | null, tick: number) {
    if (!this.open) return;
    if (!this.playing) {
      this.show(null, 'Brain', 'The brain window works on replays of a run’s checkpoints. Open one from the runs page (Watch).');
      return;
    }
    if (id === null) {
      this.show(null, 'Brain', 'Click a Terrikin to see its brain.');
      return;
    }
    const key = `${this.playing.run}/${this.playing.checkpoint}/${this.playing.seed}/${id}`;
    if (key !== this.wanted) void this.load(key, id);
    if (!this.track || this.track.head.creature !== id) return;
    this.panel.update(tick);
    this.net.draw(this.track.at(tick), performance.now());
    const last = this.track.thoughts.at(-1);
    const gone = !!last && tick > last.tick + 2 * this.track.head.brain.repeat;
    if (gone !== this.dead) {
      this.dead = gone;
      this.note(gone ? `Its last thought, at ${clock(last.tick / this.track.head.tickHz)}: it died or its place went to a hatchling.` : null);
    }
    this.fan?.update(gone ? null : at, this.track.at(tick), this.track.head);
  }

  private async load(key: string, id: number) {
    const playing = this.playing!;
    this.wanted = key;
    this.show(null, this.name(id), 'Reading its mind… the first time takes about 15 s.');
    if (!this.minds.has(key)) {
      const url = `/api/runs/${playing.run}/mind/${playing.checkpoint}?seed=${playing.seed}&creature=${id}`;
      this.minds.set(key, fetch(url).then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? `the server said ${res.status}`);
        return readMind(new Uint8Array(await res.arrayBuffer()));
      }));
    }
    try {
      const track = await this.minds.get(key)!;
      if (this.wanted !== key) return;
      log.info('mind opened', { key, thoughts: track.thoughts.length });
      this.show(track, this.panelTitle(track), null);
      void this.wire(playing, track);
      const parts = track.partsFrom(this.frames);
      if (parts !== null) this.drifted(parts, track);
    } catch (err) {
      this.minds.delete(key);
      if (this.wanted !== key) return;
      log.warn('mind not read', { key, err: String(err) });
      this.show(null, this.name(id), `Couldn’t read its mind: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // the replay was recorded on another machine and the episode came out differently here
  private drifted(tick: number, track: MindTrack) {
    const when = clock(tick / track.head.tickHz);
    if (this.playing!.here) {
      this.note(`This replay and its mind part at ${when}, though both were recorded here.`);
      return;
    }
    this.said = '';
    this.panel.say(this.panelTitle(track), {
      text: `This replay was recorded on another machine, and played here the episode parts from it at ${when}. Its brain from then on is for a different moment.`,
      action: {
        label: 'Record the replay here',
        run: () => {
          const p = this.playing!;
          this.again(new URL(`/api/runs/${p.run}/replay/${p.checkpoint}?seed=${p.seed}&here`, location.href));
        },
      },
    });
  }

  private panelTitle(track: MindTrack) {
    return `${this.name(track.head.creature)} · Terrikin ${track.head.creature}`;
  }

  // the checkpoint's strongest connections, once per checkpoint
  private async wire(playing: RunReplay, track: MindTrack) {
    const key = `${playing.run}/${playing.checkpoint}`;
    if (!this.wirings.has(key)) {
      this.wirings.set(key, fetch(`/api/runs/${playing.run}/wiring/${playing.checkpoint}`).then((res) => {
        if (!res.ok) throw new Error(`the server said ${res.status}`);
        return res.json() as Promise<Wiring>;
      }));
    }
    try {
      const wiring = await this.wirings.get(key)!;
      if (this.track === track) this.net.set(track, wiring);
    } catch (err) {
      this.wirings.delete(key);
      log.warn('wiring not read', { key, err: String(err) });
    }
  }

  private note(text: string | null) {
    this.said = '';
    if (this.track) this.panel.say(this.panelTitle(this.track), text ? { text } : null);
  }

  private show(track: MindTrack | null, title: string, note: string | null) {
    if (track !== this.track) {
      this.track = track;
      this.dead = false;
      this.panel.show(track);
      this.net.set(track, null);
      this.fan?.dispose();
      this.fan = track ? new SightFan(this.scene, track.head.rays.count) : null;
    }
    // said every frame while nothing changes, so only touch the page when it does
    if (`${title}|${note}` === this.said) return;
    this.said = `${title}|${note}`;
    this.panel.say(title, note ? { text: note } : null);
  }
}
