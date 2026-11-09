// The picker's lines of work, from the channel's index.json: a game that carries `line` belongs to one, and `question` says
// what its runs decide. Runs asking the same question are one question; a line is its questions. Out of it come what's
// being asked now, the newest answers (findings), and a card per line reading question, then runs, then answer.
import type { Channel, Game, Item, PlanRun, Row } from './pickplan';
import { runRow, watch, when } from './pickshared';

const REPO = 'https://github.com/MartianRiver/Terrarium/blob/next/docs/findings/';
// answers shown before "show all"
export const SHOWN = 6;

export type QStatus = 'asking' | 'scoring' | 'held' | 'done' | 'answered';
// file: the finding's file name, when the index has it
export interface Ref { number: string; title: string; status?: string; file?: string }
// exact: the link opens the finding itself; otherwise it opens the findings' README (no file name to build one from)
export interface Cite { number: string; title: string; status?: string; href: string; exact: boolean }
// one run of a question, drawn from the publisher's plan: progress is the words under the bar ("2.9M of 6M samples"),
// fraction how far along (0 to 1, no bar when it's done), tag where it is; href only once a replay exists
export interface RunLine {
  label: string; detail: string; state: PlanRun['state']; progress: string; fraction: number; bar: boolean; tag: string;
  href?: string; live: boolean;
}
// plan: its runs, summary: "3 runs · 6M samples each · 2 training, 1 waiting"; hold: what comes next, while it's on hold
export interface Question {
  line: string; text: string; status: QStatus; asking: boolean; at: number; note: string; href: string;
  runs: Row[]; plan: RunLine[]; summary: string; hold?: string; answers: Cite[]; seen: Cite[]; result?: string;
}
export interface LineCard { key: string; title: string; goal: string; now?: string; asking: boolean; count: string; questions: Question[] }
// asking: the cards of lines with something asking, holding just those questions; answered: every answered question,
// newest first; more: how many of them sit behind "show all"
export interface Lines { asking: LineCard[]; answered: Question[]; more: number; cards: LineCard[] }

const RANK: Record<QStatus, number> = { asking: 0, scoring: 1, held: 2, answered: 3, done: 4 };
// in a line's card: what's open first, then what's on hold, then the rest, each newest first
const ORDER: Record<QStatus, number> = { asking: 0, scoring: 0, held: 1, answered: 2, done: 2 };
const NOTE: Record<QStatus, string> = { asking: 'asking now', scoring: 'scoring', held: 'on hold', done: 'finished', answered: 'answered' };
// the queue's worker names, as they read on the page
const MACHINE: Record<string, string> = { 'river-m3': 'the Mac' };

function cite(r: Ref): Cite {
  const exact = !!r.file;
  return { number: r.number, title: r.title, status: r.status, href: `${REPO}${r.file ?? 'README.md'}`, exact };
}

function merge(into: Cite[], refs: Ref[] = []) {
  for (const r of refs) if (!into.some((c) => c.number === r.number)) into.push(cite(r));
}

export const millions = (n: number) => `${+(n / 1e6).toFixed(1)}M`;

// a run ends early (a stop rule, or a job cut short) when it's under 95% of what was planned
const SHORT = 0.95;

// the run's lines under its name: where it is on the way to its planned samples, and where it's training
export function runLine(p: PlanRun, game: string, items: Item[]): RunLine {
  const item = p.replay ? items.find((i) => i.game === game && i.replay === p.replay) : undefined;
  const fraction = p.target > 0 ? Math.min(p.samples / p.target, 1) : 0;
  const ended = p.state === 'done' && fraction < SHORT;
  const play = item?.took?.split(', ')[0];
  const progress = p.state === 'done' && !ended ? [`${millions(p.samples)} samples`, play].filter(Boolean).join(' · ')
    : p.state === 'queued' ? `${millions(p.target)} samples planned`
    : `${ended ? 'ended at ' : ''}${millions(p.samples)} of ${millions(p.target)} samples`;
  const machine = p.machine ? (MACHINE[p.machine] ?? p.machine) : '';
  const tag = { training: machine ? `training on ${machine}` : 'training', queued: 'waiting for a machine', done: 'done', stopped: 'stopped' }[p.state];
  return {
    label: p.label, detail: `seed ${p.seed} · ${p.name}`, state: p.state, progress, fraction, bar: p.state !== 'done' || ended, tag,
    href: p.replay ? watch([game], p.replay) : undefined, live: p.state === 'training',
  };
}

// "3 runs · 6M samples each · 2 training, 1 waiting"
export function summarize(plan: PlanRun[]): string {
  if (!plan.length) return '';
  const targets = plan.map((p) => p.target).filter((t) => t > 0);
  const each = !targets.length ? '' : Math.min(...targets) === Math.max(...targets) ? `${millions(targets[0])} samples each` : `up to ${millions(Math.max(...targets))} samples each`;
  const n = (state: PlanRun['state']) => plan.filter((p) => p.state === state).length;
  const states = [n('training') && `${n('training')} training`, n('queued') && `${n('queued')} waiting`, n('done') && `${n('done')} done`,
    n('stopped') && `${n('stopped')} stopped`].filter(Boolean).join(', ');
  return [`${plan.length} ${plan.length === 1 ? 'run' : 'runs'}`, each, states].filter(Boolean).join(' · ');
}

const stamp = (g: Game) => Date.parse(g.finished ?? g.started ?? '') || 0;

function questionOf(line: string, text: string, keys: string[], games: Record<string, Game>, items: Item[], now: number): Question {
  const gs = keys.map((k) => games[k]);
  const answers: Cite[] = [];
  const seen: Cite[] = [];
  for (const g of gs) { merge(answers, g.answer); merge(seen, g.seen_in); }
  const status = gs.map((g): QStatus => (g.asking ? 'asking' : (g.status as QStatus | undefined) ?? 'done'))
    .reduce((a, b) => (RANK[b] < RANK[a] ? b : a));
  const at = Math.max(...gs.map(stamp));
  const runs = keys.flatMap((k) => items.filter((i) => i.game === k).map((i): Row => {
    const row = runRow(i, k);
    return { ...row, title: row.title || i.title, live: !!games[k].training };
  }));
  const withRuns = keys.filter((k) => items.some((i) => i.game === k));
  const planned = keys.flatMap((k) => games[k].plan ?? []);
  return {
    line, text, status, asking: status === 'asking', at, runs, href: withRuns.length ? watch(withRuns) : '',
    plan: keys.flatMap((k) => (games[k].plan ?? []).map((p) => runLine(p, k, items))), summary: summarize(planned),
    hold: status === 'held' ? gs.map((g) => g.hold).find(Boolean) : undefined,
    answers, seen: seen.filter((c) => !answers.some((a) => a.number === c.number)),
    result: gs.map((g) => g.result).find(Boolean),
    note: [NOTE[status], at ? when(new Date(at).toISOString(), now) : ''].filter(Boolean).join(' · '),
  };
}

function lineCard(key: string, keys: string[], games: Record<string, Game>, items: Item[], now: number): LineCard {
  const first = games[keys[0]];
  const byQuestion = new Map<string, string[]>();
  for (const k of keys) {
    const q = games[k].question ?? games[k].goal;
    byQuestion.set(q, [...(byQuestion.get(q) ?? []), k]);
  }
  const questions = [...byQuestion].map(([text, ks]) => questionOf(key, text, ks, games, items, now))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.at - a.at);
  const n = (s: QStatus) => questions.filter((q) => q.status === s).length;
  const count = [`${questions.length} ${questions.length === 1 ? 'question' : 'questions'}`, n('answered') && `${n('answered')} answered`,
    n('held') && `${n('held')} on hold`, n('asking') && `${n('asking')} asking now`].filter(Boolean).join(' · ');
  return {
    key, title: first.family ?? first.name, goal: first.goal, now: keys.map((k) => games[k].now).find(Boolean),
    asking: n('asking') > 0, count, questions,
  };
}

export function linePlan(channel: Channel | null, now = Date.now()): Lines {
  const games = channel?.games ?? {};
  const byLine = new Map<string, string[]>();
  for (const [k, g] of Object.entries(games)) if (g.line) byLine.set(g.line, [...(byLine.get(g.line) ?? []), k]);
  const cards = [...byLine].map(([line, keys]) => lineCard(line, keys, games, channel?.items ?? [], now));
  // lines with something asking first, then the one with the newest question
  const newest = (c: LineCard) => Math.max(...c.questions.map((q) => q.at));
  cards.sort((a, b) => Number(b.asking) - Number(a.asking) || newest(b) - newest(a));
  const asking = cards.filter((c) => c.asking).map((c) => ({ ...c, questions: c.questions.filter((q) => q.asking) }));
  const answered = cards.flatMap((c) => c.questions).filter((q) => q.status === 'answered').sort((a, b) => b.at - a.at);
  return { asking, answered, more: Math.max(answered.length - SHOWN, 0), cards };
}
