// What the picker lists, worked out from the channel's and the gallery's index.json: first what's training now (and
// what finished in the last two days), each line with what it's trying and a link per run; then every game by group,
// a card per family with the question it asks and a row per setup saying what's different and how it did; then the
// main line's steps from the gallery, newest first. picker.ts draws it.
import { flatten } from './gallery';

export const CHANNEL = '/replays/nursery/index.json';
const RECENT_MS = 48 * 3600_000;
// older indexes don't say per game whether it's training: then anything updated in the last 40 min counts
const LIVE_MS = 40 * 60_000;

export type Group = 'colonies' | 'nursery' | 'experiments';
const GROUPS: { key: Group; title: string; text: string }[] = [
  { key: 'colonies', title: 'Colonies', text: 'The main world: colonies that forage, store food, get through the nights and hatch new Terrikins.' },
  { key: 'nursery', title: 'The nursery', text: 'Small worlds where baby Terrikins can’t go hungry, learning kids’ games.' },
  { key: 'experiments', title: 'Experiments', text: 'Tried on the side: holes they found, dead ends, and setups that aren’t the main line.' },
];

// family groups setups of one game under one card; variant says what's different about this one, about why,
// question what the family is trying to find out, result how it did; finished: when its last run ended (ISO).
// A nursery's games are its stages: order says where each comes, status whether it's training, on hold (a run
// left unfinished), done or planned (nothing trained on it yet)
export type Status = 'training' | 'held' | 'done' | 'planned';
export interface Game {
  name: string; kind: string; goal: string; setup?: string; training?: boolean; finished?: string;
  family?: string; variant?: string; group?: Group; question?: string; about?: string; result?: string;
  nursery?: string; order?: number; planned?: boolean; status?: Status;
}
interface Replay { label: string; replay: string; about?: string }
export interface Item {
  replay: string; title: string; game?: string; samples?: number; took?: string; stages?: Replay[]; earlier?: Replay[];
}
export interface Channel { updated: string; games?: Record<string, Game>; items: Item[] }
interface Brain { name: string; replay: string; world: string; samples: number; total: number; started?: string; finished?: string }
export interface Gallery {
  updated: string; steps: { title: string; text?: string; brains: Brain[] }[];
  training: Brain[]; latest: Brain[]; asides: (Brain & { title: string; text: string; group?: Group })[];
  working?: { title: string; text: string; group?: Group; brains: Brain[] }[];
}

// a row or card shows its note ("22.1M samples so far", "finished 20:21") small under the text; a row with no
// href has nothing to watch yet (a planned stage, or one whose first run isn't back)
export interface Row { title: string; text: string; href?: string; live?: boolean; note?: string }
export interface Card { title: string; text: string; href: string; live?: boolean; note?: string; rows: Row[]; nursery?: Nursery }
// a nursery opens to its stages; a stage opens to its checkpoints and the earlier stages' brains in its world
export interface Chip { label: string; href: string; about?: string }
export interface Stage { order: number; title: string; text: string; status: Status; note: string; took?: string; chips: Chip[]; earlier: Chip[] }
export interface Nursery { status: Status; count: string; stages: Stage[] }
export interface Section { key: string; title: string; text: string; cards: Card[]; all?: string }

export function sentence(text = '') {
  const end = text.search(/[.!?](\s|$)/);
  return end < 0 ? text : text.slice(0, end + 1);
}

export function when(iso: string, now: number) {
  const d = new Date(iso);
  const today = new Date(now).toDateString() === d.toDateString();
  return today ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

const watch = (keys: string[], start?: string, at?: string) =>
  `/watch/?channel=${CHANNEL}&game=${keys.map(encodeURIComponent).join(',')}${start ? `&start=${encodeURIComponent(start)}` : ''}${at ? `&at=${encodeURIComponent(at)}` : ''}`;
const groupOf = (g: Game): Group => g.group ?? (g.kind === 'the main world' ? 'colonies' : 'nursery');
const familyOf = (g: Game) => g.family ?? g.name;

// a setup's name on its own: never just the family's name again
function variantOf(g: Game) {
  if (g.variant) return g.variant;
  return g.name !== familyOf(g) ? g.name : sentence(g.setup) || g.name;
}

function channelSections(c: Channel, now: number): { live: Card[]; groups: Map<Group, Card[]>; all: string[] } {
  const games = c.games ?? {};
  const fresh = now - new Date(c.updated).getTime() < LIVE_MS;
  const says = Object.values(games).some((g) => g.training !== undefined);
  const training = (g: Game) => (says ? !!g.training : fresh);
  const watched = new Set(c.items.map((i) => i.game).filter((k): k is string => !!k && !!games[k]));
  // a nursery's stages are listed even with nothing to watch yet
  const keys = [...watched, ...Object.keys(games).filter((k) => games[k].nursery && !watched.has(k))];
  const live: Card[] = [];
  for (const key of watched) {
    const g = games[key];
    const recent = g.finished && now - new Date(g.finished).getTime() < RECENT_MS;
    if (!training(g) && !recent) continue;
    // each run's title is "Game · arm · seed 1 · 22.1M samples so far"
    const runs = c.items.filter((i) => i.game === key);
    // one run: the card itself opens it
    const rows = runs.length < 2 ? [] : runs.map((i) => {
      const [, arm = '', ...rest] = i.title.split(' · ');
      return { title: arm, text: '', href: watch([key], i.replay), note: rest.join(' · ') };
    });
    live.push({
      title: `${familyOf(g)}: ${variantOf(g)}`, text: [g.about ?? sentence(g.setup), g.result].filter(Boolean).join(' '),
      href: runs.length === 1 ? watch([key], runs[0].replay) : watch([key]), live: training(g), note: training(g) ? 'training now' : `finished ${when(g.finished!, now)}`, rows,
    });
  }
  const families = new Map<string, string[]>();
  for (const key of keys) {
    const id = `${groupOf(games[key])}:${familyOf(games[key])}`;
    families.set(id, [...(families.get(id) ?? []), key]);
  }
  const groups = new Map<Group, Card[]>();
  for (const all of families.values()) {
    const g = games[all[0]];
    const members = all.filter((k) => watched.has(k));
    const question = all.map((k) => games[k].question).find(Boolean) ?? g.goal;
    const card: Card = { title: familyOf(g), text: question, href: members.length ? watch(members) : '', live: all.some((k) => training(games[k])), rows: [] };
    if (g.nursery) {
      card.nursery = nursery(all, games, c.items, training, now);
      card.live = card.nursery.status === 'training';
    } else if (members.length > 1) {
      card.rows = members.map((k) => ({
        title: variantOf(games[k]), text: [games[k].about, games[k].result].filter(Boolean).join(' '),
        href: watch([k]), live: training(games[k]),
      }));
    } else {
      card.text = [question, g.about, g.result].filter(Boolean).join(' ');
    }
    groups.set(groupOf(g), [...(groups.get(groupOf(g)) ?? []), card]);
  }
  for (const [k, cards] of groups) groups.set(k, [...cards.filter((c) => c.live), ...cards.filter((c) => !c.live)]);
  return { live, groups, all: [...watched].filter((k) => groupOf(games[k]) === 'nursery') };
}

// a nursery's stages in the order they're trained, each saying whether it's training, on hold, done or to come
function nursery(keys: string[], games: Record<string, Game>, items: Item[], training: (g: Game) => boolean, now: number): Nursery {
  const stages = [...keys].sort((a, b) => (games[a].order ?? 0) - (games[b].order ?? 0)).map((k): Stage => {
    const g = games[k];
    const item = items.find((i) => i.game === k);
    const status: Status = g.status ?? (training(g) ? 'training' : !item || g.planned ? 'planned' : 'done');
    const note = { training: 'training now', held: 'on hold', planned: 'not yet in training', done: g.finished ? `finished ${when(g.finished, now)}` : 'finished' }[status];
    const chip = (r: Replay): Chip => ({ label: r.label, href: watch([k], item!.replay, r.replay), about: r.about });
    return {
      order: g.order ?? 0, title: variantOf(g), text: [g.about, g.result].filter(Boolean).join(' '), status, note,
      took: item?.took && item.samples ? `${+(item.samples / 1e6).toFixed(1)}M samples: ${item.took}` : item?.took,
      chips: item ? (item.stages ?? [{ label: 'now', replay: item.replay }]).map(chip) : [],
      earlier: item ? (item.earlier ?? []).map(chip) : [],
    };
  });
  const n = (s: Status) => stages.filter((x) => x.status === s).length;
  const status: Status = n('training') ? 'training' : n('planned') === stages.length ? 'planned' : n('held') || n('planned') ? 'held' : 'done';
  const count = [`${stages.length} stages`, n('training') && `${n('training')} training`, n('held') && `${n('held')} on hold`,
    n('planned') && `${n('planned')} to come`].filter(Boolean).join(' · ');
  return { status, count, stages };
}

function gallerySections(g: Gallery, now: number) {
  const all = flatten(g);
  const at = (b: Brain) => all.findIndex((x) => x.brain === b);
  const href = (b: Brain) => `/watch/?replay=/replays/gallery/${encodeURIComponent(b.replay)}&follow&gallery=${at(b)}`;
  const date = (b: Brain) => when(b.finished ?? b.started ?? g.updated, now);
  const live: Card[] = g.training.map((b) => ({ title: `The main line: ${b.name}`, text: `${b.world}. ${Math.round(b.total / 1e6)}M samples so far.`, href: href(b), live: true, note: 'training now', rows: [] }));
  const steps: Card[] = [];
  const ends = new Set(g.steps.map((s) => s.brains.at(-1)?.replay));
  for (const b of g.latest) {
    if (!ends.has(b.replay)) steps.push({ title: `The newest brain: ${b.name}`, text: `${b.world}. ${Math.round(b.total / 1e6)}M samples of training behind it.`, href: href(b), note: date(b), rows: [] });
  }
  for (const s of [...g.steps].reverse()) {
    const b = s.brains.at(-1);
    if (b) steps.push({ title: s.title, text: sentence(s.text), href: href(b), note: date(b), rows: [] });
  }
  const extra = new Map<Group, Card[]>();
  const put = (group: Group, card: Card) => extra.set(group, [...(extra.get(group) ?? []), card]);
  for (const w of g.working ?? []) if (w.brains[0]) put(w.group ?? 'colonies', { title: w.title, text: sentence(w.text), href: href(w.brains[0]), rows: [] });
  for (const a of g.asides) put(a.group ?? 'experiments', { title: a.title, text: sentence(a.text), href: href(a), note: date(a), rows: [] });
  return { live, steps, extra };
}

export function plan(channel: Channel | null, gallery: Gallery | null, now = Date.now()): Section[] {
  const c = channel ? channelSections(channel, now) : { live: [], groups: new Map<Group, Card[]>(), all: [] };
  const g = gallery ? gallerySections(gallery, now) : { live: [], steps: [], extra: new Map<Group, Card[]>() };
  const out: Section[] = [{
    key: 'live', title: 'Training now, and just finished',
    text: 'What’s learning now, and what finished in the last two days. Each one opens with buttons to compare it '
      + 'with random moves, the brain it started from and partway through.',
    cards: [...c.live.filter((x) => x.live), ...g.live, ...c.live.filter((x) => !x.live)],
  }];
  for (const grp of GROUPS) {
    const cards = [...(c.groups.get(grp.key) ?? []), ...(g.extra.get(grp.key) ?? [])];
    if (!cards.length) continue;
    const all = grp.key === 'nursery' && c.all.length > 1 ? watch(c.all) : undefined;
    out.push({ key: grp.key, title: grp.title, text: grp.text, cards, all });
  }
  if (g.steps.length) out.push({ key: 'story', title: 'How the colonies got here', text: 'The main line a step at a time, newest first: the best brain of each step.', cards: g.steps });
  return out;
}
