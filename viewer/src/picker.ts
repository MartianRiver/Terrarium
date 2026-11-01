// The site's /watch/ with nothing asked for: what there is to watch in plain words, over the garden playing behind.
// Training now stays open at the top; each group below opens on a tap, so the list starts short (pickplan.ts says what's in it).
import { createLogger } from './lib/logger';
import { CHANNEL, plan, type Card, type Channel, type Gallery, type Section } from './pickplan';

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

function link(href: string, ...kids: (Node | string)[]) {
  const a = document.createElement('a');
  a.href = href;
  a.append(...kids);
  return a;
}

function tag(text: string, live?: boolean) {
  return el('span', text, live ? 'picker-tag live' : 'picker-tag');
}

function card(c: Card) {
  const li = el('li', '', c.live ? 'picker-card live' : 'picker-card');
  const head = link(c.href, el('b', c.title));
  if (c.note) head.append(tag(c.note, c.live));
  head.append(el('span', c.text, 'picker-text'));
  head.className = 'picker-head';
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
