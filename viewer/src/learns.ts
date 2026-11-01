// A brain as it learns: a row of chips under a replay to switch between random moves, the brain it started as,
// about a quarter and half the way, and now, each on the same seed. A run's replay on this machine (the local
// viewer and Terrarium at Home) gets them from the runs server; a channel item on the site lists its own (`stages`).
// &learns plays them in that order, then stays on now.

import { createLogger } from './lib/logger';

const log = createLogger('learns');

interface Checkpoint { file: string; samples: number }
export interface Stop { file: string; label: string; samples: number }

const short = (n: number) => (n >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : `${Math.round(n / 1e3)}k`);

// random (the zero brain), the start (a run saves one before training; older runs have none), the checkpoints
// nearest a quarter and half of the newest, then the newest
export function stops(checkpoints: Checkpoint[]): Stop[] {
  const out: Stop[] = [{ file: 'random', label: 'random moves', samples: 0 }];
  const start = checkpoints.find((c) => c.samples === 0);
  if (start) out.push({ file: start.file, label: 'start', samples: 0 });
  const trained = checkpoints.filter((c) => c.samples > 0);
  const now = trained.at(-1);
  if (!now) return out;
  for (const share of [0.25, 0.5]) {
    const near: Checkpoint = trained.reduce((a: Checkpoint, b: Checkpoint) => (Math.abs(b.samples - share * now.samples) < Math.abs(a.samples - share * now.samples) ? b : a));
    if (near !== now && !out.some((s) => s.file === near.file)) out.push({ file: near.file, label: short(near.samples), samples: near.samples });
  }
  out.push({ file: now.file, label: `now · ${short(now.samples)}`, samples: now.samples });
  return out;
}

// /api/runs/<id>/replay/<file>?seed=N, or null for anything else
export function runReplay(url: URL | null): { id: string; file: string; seed: string } | null {
  const m = url?.pathname.match(/^\/api\/runs\/([^/]+)\/replay\/([^/]+)$/);
  return m ? { id: m[1], file: m[2], seed: url!.searchParams.get('seed') ?? '0' } : null;
}

// a chip: what it says, the replay it opens, and what a screen reader says
export interface Chip { label: string; url: URL; aria: string }

export function runChips(id: string, seed: string, list: Stop[]): Chip[] {
  return list.map((s) => ({
    label: s.label,
    url: new URL(`/api/runs/${id}/replay/${s.file}?seed=${seed}`, location.href),
    aria: s.file === 'random' ? 'Random moves, no brain' : s.samples ? `The brain after ${short(s.samples)} samples` : 'The brain it started as',
  }));
}

export class LearnsBar {
  private bar: HTMLElement | null = null;
  private run = '';
  private runStops: Stop[] = [];
  private chips: Chip[] = [];
  private at = -1;
  private title = '';

  // open: plays the replay at url (the viewer's own open, which calls show() again)
  constructor(private open: (url: URL, label: string) => void, private auto: boolean) {}

  // a replay opened: one of the chips already up keeps the row; a run's replay gets its run's; anything else none
  async show(url: URL | null) {
    const mine = url ? this.chips.findIndex((c) => c.url.href === url.href) : -1;
    if (mine >= 0) {
      this.at = mine;
      this.draw();
      return;
    }
    const here = runReplay(url);
    if (!here) {
      this.clear();
      return;
    }
    if (here.id !== this.run) {
      try {
        const res = await fetch(`/api/runs/${here.id}`, { cache: 'no-cache' });
        if (!res.ok) throw new Error(`${res.status}`);
        this.runStops = stops(((await res.json()) as { checkpoints: Checkpoint[] }).checkpoints);
        this.run = here.id;
      } catch (err) {
        // the replay still plays; only the chips are missing
        log.warn('no checkpoints for the chips', { run: here.id, error: String(err) });
        return;
      }
    }
    this.set(runChips(here.id, here.seed, this.runStops), url!, here.id.replace(/^\d{8}-\d{6}-/, ''));
  }

  // chips given outright (a channel item's stages), with the one playing
  set(chips: Chip[], playing: URL, title: string) {
    this.chips = chips;
    this.title = title;
    this.at = chips.findIndex((c) => c.url.href === playing.href);
    this.draw();
  }

  clear() {
    this.bar?.remove();
    this.bar = null;
    this.chips = [];
  }

  // a replay ran out: with &learns, on to the next stop until now
  ended(): boolean {
    if (!this.auto || this.at < 0 || this.at >= this.chips.length - 1) return false;
    this.go(this.at + 1);
    return true;
  }

  private go(i: number) {
    const chip = this.chips[i];
    log.info('switching brain', { title: this.title, stop: chip.label });
    this.open(chip.url, `${this.title} · ${chip.label}`);
  }

  private draw() {
    this.bar?.remove();
    const bar = document.createElement('nav');
    bar.id = 'learns';
    bar.setAttribute('aria-label', 'The brain as it learned');
    this.chips.forEach((c, i) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.textContent = c.label;
      chip.setAttribute('aria-pressed', String(i === this.at));
      chip.setAttribute('aria-label', c.aria);
      chip.addEventListener('click', () => this.go(i));
      bar.append(chip);
    });
    document.body.append(bar);
    this.bar = bar;
  }
}
