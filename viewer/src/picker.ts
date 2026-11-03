// The site's /watch/ with nothing asked for: what there is to watch in plain words, over the garden playing behind.
// Training now stays open at the top; each group below opens on a tap, so the list starts short (pickplan.ts says what's in it).
import { createLogger } from './lib/logger';
import { CHANNEL, plan, type Card, type Channel, type Chip, type Gallery, type Section, type Stage, type Status } from './pickplan';

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
  if (c.rows.length) {
    const rows = el('ul', '', 'picker-rows');
    for (const r of c.rows) {
      const a = link(r.href, el('b', r.title));
      if (r.live) a.append(tag('training now', true));
      if (r.text) a.append(el('span', r.text, 'picker-text'));
      if (r.note) a.append(el('span', r.note, 'picker-when'));
      const row = el('li');
      row.append(a);
      rows.append(row);
    }
    li.append(rows);
  }
  return li;
}

function section(s: Section) {
  const list = el('ol');
  list.append(...s.cards.map(card));
  if (s.key === 'live') {
    const box = el('section', '', 'picker-live');
    box.setAttribute('aria-label', s.title);
    box.append(el('h3', s.title), el('p', s.cards.length ? s.text : 'Nothing is training right now.', 'picker-about'), list);
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
    const sections = channel || gallery ? plan(channel, gallery) : [];
    log.info('picker opened', { sections: sections.map((s) => `${s.key}:${s.cards.length}`).join(' ') });
    const close = document.createElement('button');
    close.textContent = 'Just watch the garden';
    close.addEventListener('click', () => this.box.close());
    const foot = el('p', '', 'picker-foot');
    foot.append(close, link('/brains/', 'Every brain, and how they got here'));
    const body = sections.length ? sections.map(section)
      : [el('p', 'The list isn’t answering right now, so here’s the garden.', 'picker-note')];
    this.box.replaceChildren(el('h2', 'What do you want to watch?'), ...body, foot);
  }
}
