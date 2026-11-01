// ?channel: a card saying what's on screen (the game, its goal and setup, what to watch for, what the brain is
// and how well it does), so a replay of a nursery game reads as more than a blob wandering about.
// The words come from the channel's index.json, so the publisher can change them without a viewer deploy.
import type { Frame } from './world';

export interface Game {
  name: string;
  kind: string; // "a memory game"
  goal: string;
  setup: string;
  watch?: string;
  // a line that follows the replay: shown while a berry is hidden, and while one is in sight
  hidden?: string;
  shown?: string;
}

export interface Item {
  replay: string;
  title: string;
  game?: string;
  brain?: string; // "has a memory · 1.0M samples of training"
  score?: { label: string; value: number; marks: [string, number][] };
  // the same brain on the same seed as it learned: random moves, the start, partway, now (learns.ts)
  stages?: { label: string; replay: string; about?: string }[];
}

export class ChannelCard {
  private box = document.createElement('details');
  private now = document.createElement('p');
  private game: Game | null = null;
  private hidden: boolean | null = null;

  constructor(parent: HTMLElement) {
    this.box.id = 'channel';
    this.box.hidden = true;
    // a phone has room for the summary only until it's opened
    this.box.open = matchMedia('(min-width: 641px)').matches;
    parent.append(this.box);
  }

  show(item: Item, games: Record<string, Game>, place: number, count: number, note?: string) {
    this.game = (item.game && games[item.game]) || null;
    this.hidden = null;
    const g = this.game;
    this.box.replaceChildren();
    const summary = document.createElement('summary');
    summary.append(text('b', g ? g.name : item.title));
    if (g) summary.append(text('span', ` · ${g.kind}`));
    this.box.append(summary);
    if (g) {
      this.box.append(row('Goal', g.goal), row('Setup', g.setup));
      if (g.watch) this.box.append(row('Watch', g.watch));
    }
    this.now.className = 'channel-now';
    this.now.hidden = true;
    this.box.append(this.now);
    if (item.brain) this.box.append(row('This brain', item.brain));
    if (item.score) this.box.append(scoreBar(item.score));
    this.box.append(text('p', `${place + 1} of ${count} on the channel · ${note ?? 'newer brains turn up as training goes'}`, 'channel-foot'));
    this.box.hidden = false;
  }

  frame(f: Frame) {
    const g = this.game;
    if (!g?.hidden || !g.shown) return;
    const berry = f.food.find((x) => x.kind === 'common');
    const hidden = berry ? berry.hidden : null;
    if (hidden === this.hidden) return;
    this.hidden = hidden;
    this.now.hidden = hidden === null;
    this.now.dataset.hidden = String(hidden);
    this.now.replaceChildren(text('b', 'Now'), ' ', hidden ? g.hidden : g.shown);
  }
}

function text(tag: string, s: string, cls = '') {
  const el = document.createElement(tag);
  el.textContent = s;
  if (cls) el.className = cls;
  return el;
}

function row(label: string, s: string) {
  const p = document.createElement('p');
  p.append(text('b', label), ' ', s);
  return p;
}

// the brain's score on a bar from 0 to 100%, with the baselines marked on it
function scoreBar(score: NonNullable<Item['score']>) {
  const box = document.createElement('div');
  box.className = 'channel-score';
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  box.append(text('p', `${score.label} ${pct(score.value)}`, 'channel-value'));
  const bar = document.createElement('div');
  bar.className = 'channel-bar';
  bar.setAttribute('role', 'img');
  bar.setAttribute('aria-label', `${score.label} ${pct(score.value)}; ` + score.marks.map(([n, v]) => `${n} ${pct(v)}`).join(', '));
  const fill = document.createElement('span');
  fill.style.width = pct(Math.min(1, score.value));
  bar.append(fill);
  for (const [, v] of score.marks) {
    const tick = document.createElement('i');
    tick.style.left = pct(Math.min(1, v));
    bar.append(tick);
  }
  box.append(bar, text('p', score.marks.map(([n, v]) => `${n} ${pct(v)}`).join(' · '), 'channel-marks'));
  return box;
}
