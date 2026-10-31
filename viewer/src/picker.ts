// The site's /watch/ with nothing asked for: what there is to watch in plain words, over the garden playing behind,
// in groups (the colonies, the nursery, experiments), whichever is training now first and newest first in each.
import { flatten } from './gallery';
import { createLogger } from './lib/logger';

const log = createLogger('picker');
const CHANNEL = '/replays/nursery/index.json';
const GALLERY = '/replays/gallery/index.json';
// the channel's publisher rewrites its index every 10 min while anything trains
const LIVE_MS = 40 * 60_000;
// training now: newer brains turn up while you watch; on hold: its newest brain plays, but nothing's training it
const LIVE = 'training now';
const HELD = 'on hold';

type Group = 'colonies' | 'nursery' | 'experiments';
const GROUPS: { key: Group; title: string; text: string }[] = [
  { key: 'colonies', title: 'Colonies', text: 'The main world: colonies that forage, store food, get through the nights and hatch new Terrikins.' },
  { key: 'nursery', title: 'The nursery', text: 'Small worlds where baby Terrikins can’t go hungry, learning kids’ games.' },
  { key: 'experiments', title: 'Experiments', text: 'Tried on the side: holes they found, dead ends, and setups that aren’t the main line.' },
];

// training: the publisher's word on whether this game's line is training right now (older indexes don't say);
// family groups setups of the same game under one entry (Peekaboo: one look, tired, …), variant names each one there;
// group: where it's listed (a game whose kind is the main world goes with the colonies, the rest in the nursery)
interface Game { name: string; kind: string; goal: string; training?: boolean; family?: string; variant?: string; group?: Group }
interface Item { game?: string; samples?: number; brain?: string; score?: { label: string; value: number } }
interface Channel { updated: string; games?: Record<string, Game>; items: Item[] }
interface Brain {
  name: string; replay: string; world: string; samples: number; total: number;
  started?: string; finished?: string; numbers?: Record<string, unknown>;
}
interface Gallery {
  updated: string; steps: { title: string; text?: string; brains: Brain[] }[];
  training: Brain[]; latest: Brain[]; asides: (Brain & { title: string; text: string; group?: Group })[];
  working?: { title: string; text: string; group?: Group; brains: Brain[] }[];
}

interface Variant { label: string; tag: string; href: string }
interface Choice { group: Group; when: number; title: string; tag?: string; text: string; href: string; variants?: Variant[] }

function ago(when: number) {
  const m = Math.round((Date.now() - when) / 60000);
  if (m < 90) return `${Math.max(m, 1)} min ago`;
  if (m < 36 * 60) return `${Math.round(m / 60)} h ago`;
  return new Date(when).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function sentence(text = '') {
  const end = text.search(/[.!?](\s|$)/);
  return end < 0 ? text : text.slice(0, end + 1);
}

async function json<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`${res.status}`);
    return (await res.json()) as T;
  } catch (err) {
    log.warn('not read', { url, err: String(err) });
    return null;
  }
}

const groupOf = (g: Game): Group => g.group ?? (g.kind === 'the main world' ? 'colonies' : 'nursery');

function games(c: Channel): Choice[] {
  const when = new Date(c.updated).getTime();
  const live = Date.now() - when < LIVE_MS;
  const keys = [...new Set(c.items.map((i) => i.game).filter((g): g is string => !!g && !!c.games?.[g]))];
  const nursery = keys.filter((k) => groupOf(c.games![k]) === 'nursery');
  const tag = (key: string) => (c.games![key].training ?? live) ? LIVE : HELD;
  const watch = (keys: string[]) => `/watch/?channel=${CHANNEL}&game=${keys.map(encodeURIComponent).join(',')}`;
  const families = new Map<string, string[]>();
  for (const key of keys) {
    const family = `${groupOf(c.games![key])}:${c.games![key].family ?? c.games![key].name}`;
    families.set(family, [...(families.get(family) ?? []), key]);
  }
  const out: Choice[] = [...families.values()].map((members) => {
    const g = c.games![members[0]];
    const title = members.length > 1 ? (g.family ?? g.name) : g.name;
    const best = c.items.filter((i) => i.game === members[0]).sort((a, b) => (b.samples ?? 0) - (a.samples ?? 0))[0];
    const score = best.score ? ` Its newest brain: ${best.score.label.toLowerCase()} ${Math.round(best.score.value * 100)}%.` : '';
    const choice: Choice = {
      group: groupOf(g), when, title, tag: members.some((k) => tag(k) === LIVE) ? LIVE : HELD,
      text: `${g.goal}${score}`, href: watch(members),
    };
    if (members.length > 1) {
      choice.variants = members.map((k) => ({ label: c.games![k].variant ?? c.games![k].name, tag: tag(k), href: watch([k]) }));
    }
    return choice;
  });
  if (nursery.length > 1) {
    out.unshift({
      group: 'nursery', when: when + 1, title: 'All the nursery games, in turn',
      tag: nursery.some((k) => c.games![k].training ?? live) ? LIVE : HELD,
      text: 'One replay after another, newest brains as they come.',
      href: nursery.length === keys.length ? `/watch/?channel=${CHANNEL}` : watch(nursery),
    });
  }
  return out;
}

function brains(g: Gallery): Choice[] {
  const all = flatten(g);
  const at = (b: Brain) => all.findIndex((x) => x.brain === b);
  const href = (b: Brain) => `/watch/?replay=/replays/gallery/${encodeURIComponent(b.replay)}&follow&gallery=${at(b)}`;
  const time = (b: Brain) => new Date(b.finished ?? b.started ?? g.updated).getTime();
  const out: Choice[] = [];
  // the newest brain is often the last of a step: listed once, under the step's name
  const ends = new Map(g.steps.map((s) => [s.brains[s.brains.length - 1]?.replay, s]));
  for (const b of [...g.training, ...g.latest]) {
    if (ends.has(b.replay)) continue;
    out.push({ group: 'colonies', when: time(b), title: `The newest brain: ${b.name}`, tag: b.finished ? 'latest' : 'training now',
      text: `${b.world}. ${Math.round(b.total / 1e6)}M samples of training behind it.`, href: href(b) });
  }
  for (const w of g.working ?? []) {
    const b = w.brains[0];
    if (b) out.push({ group: w.group ?? 'colonies', when: time(b), title: w.title, tag: 'working on', text: sentence(w.text), href: href(b) });
  }
  for (const s of g.steps) {
    const b = s.brains[s.brains.length - 1];
    const newest = [...g.training, ...g.latest].find((x) => x.replay === b?.replay);
    if (b) out.push({ group: 'colonies', when: time(newest ?? b), title: s.title, tag: newest ? 'latest' : undefined, text: sentence(s.text), href: href(newest ?? b) });
  }
  for (const a of g.asides) out.push({ group: a.group ?? 'experiments', when: time(a), title: a.title, tag: 'on the side', text: sentence(a.text), href: href(a) });
  return out;
}

export class Picker {
  private box = document.createElement('dialog');

  // onDismiss: closed without picking anything
  constructor(parent: HTMLElement, onDismiss?: () => void) {
    this.box.id = 'picker';
    if (onDismiss) this.box.addEventListener('close', onDismiss);
    this.box.setAttribute('aria-label', 'What to watch');
    this.box.addEventListener('click', (e) => { if (e.target === this.box) this.box.close(); });
    parent.append(this.box);
  }

  private list(choices: Choice[]) {
    const list = document.createElement('ol');
    for (const c of choices) {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = c.href;
      a.append(el('b', c.title));
      if (c.tag) a.append(el('span', c.tag, c.tag === LIVE ? 'picker-tag live' : c.tag === HELD ? 'picker-tag held' : 'picker-tag'));
      a.append(el('span', c.text, 'picker-text'), el('span', ago(c.when), 'picker-when'));
      li.append(a);
      // setups of the same game, each on its own
      if (c.variants) {
        const row = el('p', '', 'picker-variants');
        for (const v of c.variants) {
          const chip = document.createElement('a');
          chip.href = v.href;
          chip.className = v.tag === LIVE ? 'live' : '';
          chip.textContent = v.label;
          chip.title = v.tag;
          row.append(chip);
        }
        li.append(row);
      }
      list.append(li);
    }
    return list;
  }

  async open() {
    this.box.replaceChildren(el('h2', 'What do you want to watch?'), el('p', 'Loading…', 'picker-note'));
    if (!this.box.open) this.box.showModal();
    const [channel, gallery] = await Promise.all([json<Channel>(CHANNEL), json<Gallery>(GALLERY)]);
    const choices = [...(channel ? games(channel) : []), ...(gallery ? brains(gallery) : [])].sort((a, b) => b.when - a.when);
    const sections = GROUPS.map((g) => ({ ...g, choices: choices.filter((c) => c.group === g.key) }))
      .filter((g) => g.choices.length)
      .sort((a, b) => Number(live(b.choices)) - Number(live(a.choices)) || b.choices[0].when - a.choices[0].when);
    const lists = sections.map((g) => {
      const section = document.createElement('section');
      section.setAttribute('aria-label', g.title);
      section.append(el('h3', g.title), el('p', g.text, 'picker-about'), this.list(g.choices));
      return section;
    });
    const close = document.createElement('button');
    close.textContent = 'Just watch the garden';
    close.addEventListener('click', () => this.box.close());
    const more = document.createElement('a');
    more.href = '/brains/';
    more.textContent = 'Every brain, and how they got here';
    const foot = el('p', '', 'picker-foot');
    foot.append(close, more);
    const key = el('p', '', 'picker-key');
    key.append(el('span', LIVE, 'picker-tag live'), ' newer brains turn up while you watch · ', el('span', HELD, 'picker-tag held'), ' its newest brain, not training right now');
    this.box.replaceChildren(el('h2', 'What do you want to watch?'), key,
      ...(lists.length ? lists : [el('p', 'Nothing to pick from right now, so here’s the garden.', 'picker-note')]), foot);
  }
}

const live = (choices: Choice[]) => choices.some((c) => c.tag === LIVE || c.tag === 'training now');

function el(tag: string, text: string, cls?: string) {
  const e = document.createElement(tag);
  e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
