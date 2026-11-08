// The picker's lines of work, from the channel's index.json: a game that carries `line` belongs to one, and `question` says
// what its runs decide. Runs asking the same question are one question; a line is its questions. Out of it come what's
// being asked now, the newest answers (findings), and a card per line reading question, then runs, then answer.
import type { Channel, Game, Item, Row } from './pickplan';
import { runRow, watch, when } from './pickshared';

const REPO = 'https://github.com/MartianRiver/Terrarium/blob/next/docs/findings/';
// answers shown before "show all"
export const SHOWN = 6;

export type QStatus = 'asking' | 'scoring' | 'done' | 'answered';
// file: the finding's file name, when the index has it
export interface Ref { number: string; title: string; status?: string; file?: string }
// exact: the link opens the finding itself; otherwise it opens the findings' README (no file name to build one from)
export interface Cite { number: string; title: string; status?: string; href: string; exact: boolean }
export interface Question {
  line: string; text: string; status: QStatus; asking: boolean; at: number; note: string; href: string;
  runs: Row[]; answers: Cite[]; seen: Cite[]; result?: string;
}
export interface LineCard { key: string; title: string; goal: string; now?: string; asking: boolean; count: string; questions: Question[] }
// asking: the cards of lines with something asking, holding just those questions; answered: every answered question,
// newest first; more: how many of them sit behind "show all"
export interface Lines { asking: LineCard[]; answered: Question[]; more: number; cards: LineCard[] }

const RANK: Record<QStatus, number> = { asking: 0, scoring: 1, answered: 2, done: 3 };
const NOTE: Record<QStatus, string> = { asking: 'asking now', scoring: 'scoring', done: 'finished', answered: 'answered' };

function cite(r: Ref): Cite {
  const exact = !!r.file;
  return { number: r.number, title: r.title, status: r.status, href: `${REPO}${r.file ?? 'README.md'}`, exact };
}

function merge(into: Cite[], refs: Ref[] = []) {
  for (const r of refs) if (!into.some((c) => c.number === r.number)) into.push(cite(r));
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
  return {
    line, text, status, asking: status === 'asking', at, runs, href: withRuns.length ? watch(withRuns) : '',
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
  const questions = [...byQuestion].map(([text, ks]) => questionOf(key, text, ks, games, items, now)).sort((a, b) => b.at - a.at);
  const n = (s: QStatus) => questions.filter((q) => q.status === s).length;
  const count = [`${questions.length} ${questions.length === 1 ? 'question' : 'questions'}`, n('answered') && `${n('answered')} answered`,
    n('asking') && `${n('asking')} asking now`].filter(Boolean).join(' · ');
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
  cards.sort((a, b) => Number(b.asking) - Number(a.asking) || b.questions[0].at - a.questions[0].at);
  const asking = cards.filter((c) => c.asking).map((c) => ({ ...c, questions: c.questions.filter((q) => q.asking) }));
  const answered = cards.flatMap((c) => c.questions).filter((q) => q.status === 'answered').sort((a, b) => b.at - a.at);
  return { asking, answered, more: Math.max(answered.length - SHOWN, 0), cards };
}
