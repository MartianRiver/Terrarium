// The site's /watch/ with nothing asked for: what there is to watch in plain words, over the garden playing behind.
// What's being asked now stays open at the top, then the newest answers and a card per line of work (lines.ts); the groups
// below open on a tap, so the list starts short (pickplan.ts says what's in them).
import { createLogger } from './lib/logger';
import { linePlan, type Cite, type LineCard, type Lines, type Question, type RunLine } from './lines';
import { CHANNEL, plan, type Card, type Channel, type Chip, type Gallery, type Row, type Section, type Stage, type Status } from './pickplan';

const log = createLogger('picker');
const GALLERY = '/replays/gallery/index.json';

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

function el(tag: string, text = '', cls?: string) {
  const e = document.createElement(tag);
  e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

// nothing to watch yet: the same layout, not a link
function link(href: string | undefined, ...kids: (Node | string)[]) {
  const a = document.createElement(href ? 'a' : 'div');
  if (href) (a as HTMLAnchorElement).href = href;
  else a.className = 'picker-off';
  a.append(...kids);
  return a;
}

function tag(text: string, live?: boolean) {
  return el('span', text, live ? 'picker-tag live' : 'picker-tag');
}

function tagFor(status: Status, text: string) {
  return el('span', text, `picker-tag ${status}`);
}

function chips(label: string, list: Chip[]) {
  const p = el('p', '', 'picker-chips');
  p.append(el('span', label, 'picker-chips-label'));
  for (const c of list) {
    const a = link(c.href, c.label);
    if (c.about) a.title = c.about;
    p.append(a);
  }
  return p;
}

// a stage with something to watch opens to its checkpoints; one still to come is a greyed line
function stage(s: Stage) {
  const li = el('li', '', `picker-stage ${s.status}`);
  const head = [el('b', `${s.order}. ${s.title}`), tagFor(s.status, s.note)];
  if (!s.chips.length) {
    const off = el('div', '', 'picker-off');
    off.append(...head, el('span', s.text, 'picker-text'));
    if (s.pass) off.append(el('span', `Moves on when: ${s.pass}`, 'picker-pass'));
    li.append(off);
    return li;
  }
  const box = document.createElement('details');
  const summary = document.createElement('summary');
  summary.append(...head);
  if (s.took) summary.append(el('span', s.took, 'picker-when'));
  box.append(summary, el('p', s.text, 'picker-text'));
  if (s.pass) box.append(el('p', `Moves on when: ${s.pass}`, 'picker-pass'));
  box.append(chips('Watch it learn:', s.chips));
  if (s.earlier.length) box.append(chips('Earlier stages’ brains here:', s.earlier));
  li.append(box);
  return li;
}

// a nursery opens to its stages in order: what's done, what's training, what's on hold and what's to come
function nursery(c: Card) {
  const n = c.nursery!;
  const li = el('li', '', c.live ? 'picker-card live' : 'picker-card');
  const box = document.createElement('details');
  box.className = 'picker-nursery';
  const summary = document.createElement('summary');
  summary.append(el('b', c.title), tagFor(n.status, { training: 'training now', held: 'on hold', done: 'finished', planned: 'to come' }[n.status]),
    el('span', c.text, 'picker-text'), el('span', n.count, 'picker-when'));
  box.append(summary);
  if (c.href) {
    const all = link(c.href, 'Watch every stage, one after another');
    all.className = 'picker-all';
    box.append(all);
  }
  // what's training, on hold or just finished shows straight away; older stages and those to come fold away
  const older = n.stages.filter((s) => s.status === 'done' && !s.recent);
  const later = n.stages.filter((s) => s.status === 'planned');
  let now = n.stages.filter((s) => !older.includes(s) && !later.includes(s));
  if (!now.length && older.length) now = [older.pop()!];
  if (n.now) {
    const at = el('p', '', 'picker-now');
    at.append(el('b', 'Where it’s at: '), n.now);
    box.append(at);
  }
  if (older.length) box.append(fold(`${older.length} earlier ${older.length === 1 ? 'stage' : 'stages'}, finished`, older));
  box.append(stages(now));
  // open, so what's planned next is in view
  if (later.length) box.append(fold(`${later.length} to come`, later, true));
  li.append(box);
  return li;
}

function stages(list: Stage[]) {
  // numbered by where each comes in the nursery, not by where it sits in this list
  const ol = el('ol', '', 'picker-stages');
  ol.append(...list.map(stage));
  return ol;
}

function fold(label: string, list: Stage[], open = false) {
  const box = document.createElement('details');
  box.className = 'picker-fold';
  box.open = open;
  box.append(el('summary', label), stages(list));
  return box;
}

function card(c: Card) {
  if (c.nursery) return nursery(c);
  const li = el('li', '', c.live ? 'picker-card live' : 'picker-card');
  const head = link(c.href, el('b', c.title));
  if (c.note) head.append(tag(c.note, c.live));
  head.append(el('span', c.text, 'picker-text'));
  head.classList.add('picker-head');
  li.append(head);
  if (c.rows.length) li.append(rows(c.rows));
  return li;
}

function rows(list: Row[]) {
  const ul = el('ul', '', 'picker-rows');
  for (const r of list) {
    const a = link(r.href, el('b', r.title));
    if (r.live) a.append(tag('training now', true));
    if (r.text) a.append(el('span', r.text, 'picker-text'));
    if (r.note) a.append(el('span', r.note, 'picker-when'));
    const row = el('li');
    row.append(a);
    ul.append(row);
  }
  return ul;
}

// a run from a question's plan: what makes it its own, which seed, how far along it is and where it trains; a link only
// once a replay exists
function planRows(list: RunLine[]) {
  const ul = el('ul', '', 'picker-rows picker-plan');
  for (const r of list) {
    const a = link(r.href, el('b', r.label), el('span', r.detail, 'picker-when'));
    if (r.bar) {
      const bar = el('span', '', 'picker-bar');
      bar.setAttribute('role', 'progressbar');
      bar.setAttribute('aria-label', `${r.detail}, ${r.progress}`);
      bar.setAttribute('aria-valuemin', '0');
      bar.setAttribute('aria-valuemax', '100');
      bar.setAttribute('aria-valuenow', String(Math.round(r.fraction * 100)));
      const fill = el('i');
      fill.style.width = `${r.fraction > 0 ? Math.max(r.fraction * 100, 2) : 0}%`;
      bar.append(fill);
      a.append(bar);
    }
    a.append(el('span', r.progress, 'picker-progress'), el('span', r.tag, r.state === 'training' ? 'picker-tag training' : r.state === 'stopped' ? 'picker-tag held' : 'picker-tag'));
    const row = el('li');
    row.append(a);
    ul.append(row);
  }
  return ul;
}

// what a question has to show: its plan's runs, or the replays alone when the index carries no plan
function runList(q: Question) {
  if (!q.plan.length) return q.runs.length ? rows(q.runs) : null;
  return planRows(q.plan);
}

function cited(c: Cite, text: string) {
  const a = link(c.href, text);
  a.title = c.exact ? c.title : `${c.title} (opens the findings list)`;
  return a;
}

// what a question came to: the finding that settled it, the others that mention its runs, or its numbers and "no finding yet"
function outcome(q: Question) {
  const out: HTMLElement[] = [];
  for (const c of q.answers) {
    const p = el('p', '', 'picker-answer');
    p.append(cited(c, `finding ${c.number}: ${c.title}`));
    if (c.status) p.append(el('span', c.status, 'picker-tag'));
    out.push(p);
  }
  if (!q.answers.length && q.status !== 'asking') out.push(el('p', [q.result, 'No finding yet.'].filter(Boolean).join(' '), 'picker-answer none'));
  if (q.hold) out.push(el('p', `Next: ${q.hold}`, 'picker-answer next'));
  if (q.seen.length) {
    const p = el('p', 'also in ', 'picker-seen');
    q.seen.forEach((c, i) => p.append(...(i ? [', '] : []), cited(c, c.number)));
    out.push(p);
  }
  return out;
}

// the question, what it came to, then its runs: open while it's being asked, folded away once it's done
function question(q: Question, line?: string) {
  const li = el('li', '', q.asking ? 'picker-card picker-q live' : 'picker-card picker-q');
  const head = document.createElement(q.href ? 'a' : 'div');
  if (q.href) (head as HTMLAnchorElement).href = q.href;
  head.className = 'picker-head';
  head.append(el('b', q.text), q.status === 'held' ? tagFor('held', q.note) : tag(q.note, q.asking));
  if (line) head.append(el('span', line, 'picker-when'));
  li.append(head, ...outcome(q));
  const list = runList(q);
  if (q.asking) {
    if (q.summary) li.append(el('p', q.summary, 'picker-summary'));
    if (list) li.append(list);
    if (!q.plan.some((r) => r.href) && !q.runs.length) li.append(el('p', 'First replays come when a checkpoint lands.', 'picker-answer none'));
  } else if (list) {
    const count = q.plan.length || q.runs.length;
    const box = document.createElement('details');
    box.className = 'picker-fold';
    box.append(el('summary', `${count} ${count === 1 ? 'run' : 'runs'}`), list);
    li.append(box);
  }
  return li;
}

function questions(list: Question[], lineOf?: (q: Question) => string | undefined) {
  const ol = el('ol');
  ol.append(...list.map((q) => question(q, lineOf?.(q))));
  return ol;
}

// what's being asked now: each line with something asking, its goal, the question and the live runs. Shown even when empty
function askingNow(l: Lines) {
  const box = el('section', '', 'picker-live');
  box.setAttribute('aria-label', 'Asking now');
  box.append(el('h3', 'Asking now'));
  if (!l.asking.length) {
    box.append(el('p', 'Nothing is being asked right now.', 'picker-about'));
    return box;
  }
  for (const c of l.asking) {
    const line = el('div', '', 'picker-line');
    line.append(el('b', c.title), el('span', c.goal, 'picker-about'), questions(c.questions));
    box.append(line);
  }
  return box;
}

function latestAnswers(l: Lines) {
  const box = el('section', '', 'picker-answers');
  box.setAttribute('aria-label', 'Latest answers');
  box.append(el('h3', 'Latest answers'));
  const name = (q: Question) => l.cards.find((c) => c.key === q.line)?.title;
  const show = l.answered.slice(0, l.answered.length - l.more);
  box.append(el('p', 'Questions the runs have settled, newest first.', 'picker-about'), questions(show, name));
  if (l.more) {
    const rest = document.createElement('details');
    rest.className = 'picker-fold';
    rest.append(el('summary', `Show all ${l.answered.length}`), questions(l.answered.slice(show.length), name));
    box.append(rest);
  }
  return box;
}

// a line reads as question, runs, answer; open while something is being asked
function lineCard(c: LineCard) {
  const li = el('li', '', c.asking ? 'picker-card live' : 'picker-card');
  const box = document.createElement('details');
  box.className = 'picker-nursery';
  box.open = c.asking;
  const summary = document.createElement('summary');
  summary.append(el('b', c.title), ...(c.asking ? [tag('asking now', true)] : []), el('span', c.goal, 'picker-text'), el('span', c.count, 'picker-when'));
  box.append(summary);
  if (c.now) box.append(el('p', c.now, 'picker-now'));
  box.append(questions(c.questions));
  li.append(box);
  return li;
}

function lineCards(l: Lines) {
  const box = el('section', '', 'picker-lines');
  box.setAttribute('aria-label', 'Lines of work');
  const ol = el('ol');
  ol.append(...l.cards.map(lineCard));
  box.append(el('h3', 'Lines of work'), el('p', 'Each line of work is a goal, the questions asked on the way, and what the runs found.', 'picker-about'), ol);
  return box;
}

function section(s: Section) {
  const list = el('ol');
  list.append(...s.cards.map(card));
  if (s.key === 'live') {
    const box = el('section', '', 'picker-live');
    box.setAttribute('aria-label', s.title);
    box.append(el('h3', s.title), el('p', s.text, 'picker-about'), list);
    return box;
  }
  const box = document.createElement('details');
  const summary = document.createElement('summary');
  const live = s.cards.filter((c) => c.live).length;
  summary.append(el('h3', s.title), el('span', `${s.cards.length} to watch${live ? ` · ${live} training` : ''}`, 'picker-count'),
    el('span', s.text, 'picker-about'));
  box.append(summary);
  if (s.all) {
    const all = link(s.all, 'Watch them all, one after another');
    all.className = 'picker-all';
    box.append(all);
  }
  box.append(list);
  return box;
}

// closed by default: what the words on this list mean, for someone who has never trained a brain
const HELP: [string, string][] = [
  ['A question', 'is what a batch of runs is there to decide, like which starting brain learns to graze best.'],
  ['A run', 'is one brain trained by one recipe. Its label says what makes it different from the others, such as which brain it started from.'],
  ['A seed', 'is the random start a run begins from. Runs with the same label and a different seed are the same recipe tried again, there to show a result isn’t luck.'],
  ['Samples', 'are moments of play the brain learned from: the more it has, the longer it has practised. The bar shows how many of the planned samples a run has done, and a finished run says how many days of play that was.'],
  ['The tag', 'says whether a run is training now and on which computer, waiting for one, or done. A run opens to watch once its first replay is recorded.'],
  ['A finding', 'is the written answer once a batch settles its question; its number links to it. Until then a question says what the runs showed so far.'],
  ['On hold', 'means the question is paused with a plan, and the card says what comes next.'],
];

function help() {
  const box = document.createElement('details');
  box.className = 'picker-help';
  box.append(el('summary', 'How to read this'));
  const dl = el('dl');
  for (const [term, text] of HELP) dl.append(el('dt', term), el('dd', text));
  box.append(dl);
  return box;
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

  async open() {
    this.box.replaceChildren(el('h2', 'What do you want to watch?'), el('p', 'Loading…', 'picker-note'));
    if (!this.box.open) this.box.showModal();
    const [channel, gallery] = await Promise.all([json<Channel>(CHANNEL), json<Gallery>(GALLERY)]);
    // the live list outside the lines only shows when it has something; "asking now" is the one that always does
    const sections = (channel || gallery ? plan(channel, gallery) : []).filter((s) => s.key !== 'live' || s.cards.length);
    const lines = channel ? linePlan(channel) : null;
    log.info('picker opened', { sections: sections.map((s) => `${s.key}:${s.cards.length}`).join(' '), asking: lines?.asking.length, answered: lines?.answered.length });
    const close = document.createElement('button');
    close.textContent = 'Just watch the garden';
    close.addEventListener('click', () => this.box.close());
    const foot = el('p', '', 'picker-foot');
    foot.append(close, link('/brains/', 'Every brain, and how they got here'));
    const top = lines ? [askingNow(lines), ...(lines.answered.length ? [latestAnswers(lines)] : []), ...(lines.cards.length ? [lineCards(lines)] : [])] : [];
    const body = sections.length || top.length ? [...top, ...sections.map(section)]
      : [el('p', 'The list isn’t answering right now, so here’s the garden.', 'picker-note')];
    this.box.replaceChildren(el('h2', 'What do you want to watch?'), ...(lines ? [help()] : []), ...body, foot);
  }
}
