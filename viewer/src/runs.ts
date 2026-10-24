// The runs page: training runs from `python -m terrarium.serve`, their curves,
// and every checkpoint as a generation to watch in the 3D viewer. Random is
// generation 0 for a run trained from scratch, since that's how it starts out.

import { compact, lineChart, type Chart, type Series } from './charts';
import { createLogger } from './lib/logger';

const log = createLogger('runs');

const POLL_MS = 5000;

type State = 'live' | 'finished' | 'stopped';
type Evals = Record<'random' | 'brain', { food_per_minute: number; seconds_alive: number }>;

interface RunSummary {
  id: string;
  started: string;
  finished: string | null;
  state: State;
  scratch: boolean;
  world: string;
  device: string | null;
  gpu: string | null;
  hardware: string;
  samples: number;
  target: number;
  seconds: number;
  evals: Evals | null;
}

type Row = Record<string, number | number[] | undefined>;
interface Score { mean: number; stderr: number }
interface Machine { hardware: string; runs: number; hours: number; dollars: number }
interface Behind { runs: { id: string; hardware: string; hours: number; dollars: number }[]; hardware: Machine[];
  hours: number; dollars: number; missing: string | null }
interface Everything { hardware: Machine[]; hours: number; dollars: number; unused: { rentals: number; dollars: number } }

interface RunDetail {
  run: { id: string; started: string; finished?: string; scratch: boolean; device?: string; gpu?: string | null;
    workers?: number; parent: { id: string } | null; world: { file: string }; train: { config: { ppo: { samples: number } } } };
  state: State;
  metrics: Row[];
  checkpoints: { file: string; samples: number }[];
  evals: ({ checkpoint: string } & Record<'random' | 'brain', Record<'food_per_minute' | 'seconds_alive', Score>>) | null;
  compute: Behind;
}

class ServerError extends Error {}

const main = document.getElementById('runs')!;
const status = document.getElementById('status')!;
let showing = 0;

function setStatus(kind: 'loading' | 'empty' | 'error' | 'ok', text = '') {
  status.dataset.kind = kind;
  status.textContent = text;
  status.hidden = kind === 'ok';
}

// props are element properties (textContent, className, href...), not attributes
function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Record<string, unknown> = {}, ...kids: (Node | string)[]) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  node.append(...kids);
  return node;
}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { cache: 'no-store' });
  } catch (err) {
    throw new ServerError(`can't reach the runs server (${String(err)})`);
  }
  // Vite's proxy answers 5xx with an empty body when serve.py isn't running
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ServerError(body?.error ?? 'the runs server isn’t running. From sim/:\nuv run python -m terrarium.serve');
  return body as T;
}

const minutes = (s: number) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
// run.json's offsets are +1100; Date wants +11:00
const parse = (stamp: string) => new Date(stamp.replace(/([+-]\d\d)(\d\d)$/, '$1:$2'));
const when = (stamp: string) => parse(stamp).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
const name = (id: string) => id.split('-').slice(2).join('-');
const hours = (h: number) => (h < 1 ? `${Math.round(h * 60)} min` : `${h.toFixed(1)} h`);
const dollars = (d: number) => (d ? `$${d.toFixed(2)}` : '–');

function badge(state: State, scratch: boolean) {
  const out = el('span', { className: 'badges' }, el('span', { className: `badge ${state}`, textContent: state }));
  if (scratch) out.append(el('span', { className: 'badge scratch', textContent: 'scratch' }));
  return out;
}

// per machine, then the total; extra rows (rentals that never ran anything) go before the total
function machines(rows: Machine[], total: { hours: number; dollars: number }, extra: HTMLElement[] = []) {
  const head = el('tr', {}, ...['on', 'runs', 'time', 'cost'].map((h) => el('th', { textContent: h, scope: 'col' })));
  const row = (on: string, runs: string, h: string, d: string, className = '') =>
    el('tr', { className }, el('td', { textContent: on }), ...[runs, h, d].map((t) => el('td', { className: 'num', textContent: t })));
  return el('table', { className: 'compute' }, el('thead', {}, head), el('tbody', {},
    ...rows.map((m) => row(m.hardware, String(m.runs), hours(m.hours), dollars(m.dollars))),
    ...extra,
    row('in all', String(rows.reduce((n, m) => n + m.runs, 0)), hours(total.hours), dollars(total.dollars), 'total')));
}

function behind(c: Behind) {
  const runs = el('ol', { className: 'line' }, ...c.runs.map((r) => el('li', {},
    el('a', { href: `#${r.id}`, textContent: name(r.id) }), ` · ${r.hardware} · ${hours(r.hours)}${r.dollars ? ` · ${dollars(r.dollars)}` : ''}`)));
  const notes = [el('p', { className: 'none', textContent:
    'This run and every run behind its parent brain, back to the first. A run this one carried on from partway counts up to that checkpoint. ' +
    'A rented machine’s bill is shared across the runs it hosted by their hours, idle time included.' })];
  if (c.missing) notes.push(el('p', { className: 'none', textContent: `Plus whatever made ${c.missing.slice(0, 12)}, which isn’t in runs/.` }));
  return [el('h2', { textContent: 'Compute behind this brain' }), machines(c.hardware, c), runs, ...notes];
}

function everything(c: Everything) {
  const unused = c.unused.rentals
    ? [el('tr', {}, el('td', { textContent: `${c.unused.rentals} rented that never ran anything` }),
      ...['–', '–', dollars(c.unused.dollars)].map((t) => el('td', { className: 'num', textContent: t })))]
    : [];
  return [el('h2', { textContent: 'All training so far' }), machines(c.hardware, c, unused),
    el('p', { className: 'none', textContent: 'Every run here, dead ends included, and every rented machine in sim/compute.toml.' })];
}

async function showList(ticket: number) {
  const [runs, total] = await Promise.all([get<RunSummary[]>('/api/runs'), get<Everything>('/api/compute')]);
  if (ticket !== showing) return;
  document.title = 'Runs · Terrarium';
  if (!runs.length) {
    main.replaceChildren();
    return setStatus('empty', 'No runs yet. From sim/: uv run python -m terrarium.train NAME --world configs/solo.toml');
  }
  const rows = runs.map((r) => {
    const link = el('a', { href: `#${r.id}`, textContent: name(r.id) });
    const food = r.evals ? `${r.evals.brain.food_per_minute.toFixed(1)} (random ${r.evals.random.food_per_minute.toFixed(2)})` : '–';
    return el('tr', {},
      el('td', {}, link, badge(r.state, r.scratch)),
      el('td', { textContent: when(r.started) }),
      el('td', { className: 'num', textContent: `${compact(r.samples)} / ${compact(r.target)}` }),
      el('td', { className: 'num', textContent: minutes(r.seconds) }),
      el('td', { textContent: r.hardware }),
      el('td', { className: 'num', textContent: food }));
  });
  const head = el('tr', {}, ...['run', 'started', 'samples', 'time', 'on', 'food a minute'].map((h) => el('th', { textContent: h, scope: 'col' })));
  main.replaceChildren(el('h1', { textContent: 'Runs' }), el('table', { className: 'runs' }, el('thead', {}, head), el('tbody', {}, ...rows)),
    ...everything(total));
  setStatus('ok');
  if (runs.some((r) => r.state === 'live')) setTimeout(() => ticket === showing && void refresh(), POLL_MS);
}

function charts(d: RunDetail) {
  const rows = d.metrics;
  const xs = rows.map((r) => r.samples as number);
  const pick = (key: string) => rows.map((r) => (typeof r[key] === 'number' ? (r[key] as number) : null));
  const spread = (k: number) => rows.map((r) => (Array.isArray(r.std) ? r.std[k] : null));
  const specs: [string, Series[]][] = [
    ['Food per episode (−1 if it died)', [{ name: 'return', values: pick('episode_return') }]],
    ['Seconds alive per episode', [{ name: 'seconds', values: pick('episode_seconds') }]],
    ['Samples a second', [{ name: 'samples/s', values: pick('samples_per_second') }]],
    ['Action spread (std)', [{ name: 'thrust', values: spread(0) }, { name: 'turn', values: spread(1) }]],
    ['KL per update', [{ name: 'kl', values: pick('kl') }]],
    ['Explained variance', [{ name: 'explained', values: pick('explained_variance') }]],
  ];
  const all: Chart[] = [];
  const hover = (i: number | null) => all.forEach((c) => c.show(i));
  for (const [title, series] of specs) all.push(lineChart(title, xs, series, hover));
  return el('div', { className: 'charts' }, ...all.map((c) => c.el));
}

function generations(d: RunDetail) {
  const evals = d.evals;
  const fmt = (s: Record<'food_per_minute' | 'seconds_alive', Score>) =>
    `${s.food_per_minute.mean.toFixed(1)} food/min · ${Math.round(s.seconds_alive.mean)} s alive`;
  // a run carrying on from a parent starts from that brain, not from random
  const first = d.run.parent ? [] : [{ file: 'random', samples: 0 }];
  const watches: [HTMLAnchorElement, string, string][] = [];
  const cards = [...first, ...d.checkpoints].map((c, i) => {
    const gen = i + 1 - first.length;
    const label = gen ? `gen ${gen} · ${compact(c.samples)} samples` : 'gen 0 · random';
    const score = gen === 0 && evals ? fmt(evals.random) : evals?.checkpoint === c.file ? fmt(evals.brain) : '';
    const watch = el('a', { className: 'watch', textContent: 'Watch', target: '_blank' });
    watch.setAttribute('aria-label', `Watch ${label}`);
    watches.push([watch, c.file, label]);
    return el('li', {}, el('strong', { textContent: label }), el('span', { className: 'score', textContent: score || ' ' }), watch);
  });
  const setSeed = (seed: number) => {
    for (const [watch, file, label] of watches) {
      const replay = `/api/runs/${d.run.id}/replay/${file}?seed=${seed}`;
      watch.href = `/?${new URLSearchParams({ replay, name: `${name(d.run.id)} ${label}` })}`;
    }
  };
  setSeed(seedValue);
  return { el: el('ol', { className: 'gens' }, ...cards), setSeed };
}

function table(d: RunDetail) {
  // one row per checkpoint, the curves' numbers for anyone not hovering
  const at = new Set(d.checkpoints.map((c) => c.samples));
  const keys = ['samples', 'episode_return', 'episode_seconds', 'samples_per_second', 'kl', 'explained_variance'];
  const rows = d.metrics.filter((r) => at.has(r.samples as number)).map((r) =>
    el('tr', {}, ...keys.map((k) => el('td', { className: 'num', textContent: typeof r[k] === 'number' ? compact(r[k] as number) : '–' }))));
  const box = el('details', { open: tableOpen }, el('summary', { textContent: 'Numbers at each checkpoint' }),
    el('table', {}, el('thead', {}, el('tr', {}, ...keys.map((k) => el('th', { textContent: k.replace(/_/g, ' '), scope: 'col' })))),
      el('tbody', {}, ...rows)));
  box.addEventListener('toggle', () => (tableOpen = box.open));
  return box;
}

// kept across the refreshes of a live run
let seedValue = 0;
let tableOpen = false;

async function showRun(id: string, ticket: number) {
  const d = await get<RunDetail>(`/api/runs/${encodeURIComponent(id)}`);
  if (ticket !== showing) return;
  // don't rebuild the page under someone typing a seed; catch the next poll
  if (document.activeElement?.id === 'seed' && d.state === 'live') return void setTimeout(() => ticket === showing && void refresh(), POLL_MS);
  const r = d.run;
  document.title = `${name(r.id)} · Runs · Terrarium`;
  const last = d.metrics.at(-1);
  const seconds = r.finished ? (parse(r.finished).getTime() - parse(r.started).getTime()) / 1000 : undefined;
  const facts = [
    `${compact((last?.samples as number) ?? 0)} of ${compact(r.train.config.ppo.samples)} samples`,
    minutes(seconds ?? (last?.seconds as number) ?? 0),
    r.world.file, d.compute.runs[0].hardware, r.workers && `${r.workers} worker${r.workers > 1 ? 's' : ''}`, `started ${when(r.started)}`,
  ].filter(Boolean);
  const gens = generations(d);
  const seedInput = el('input', { type: 'number', min: '0', step: '1', value: String(seedValue), id: 'seed' });
  seedInput.addEventListener('input', () => {
    seedValue = Math.max(0, Math.floor(Number(seedInput.value)) || 0);
    gens.setSeed(seedValue);
  });
  const body = d.metrics.length ? [charts(d), table(d)] : [el('p', { className: 'none', textContent: 'No updates yet.' })];
  main.replaceChildren(
    el('p', {}, el('a', { href: '#', textContent: '← all runs' })),
    el('h1', {}, name(r.id), badge(d.state, r.scratch)),
    el('p', { className: 'facts', textContent: facts.join(' · ') }),
    el('h2', { textContent: 'Generations' }),
    el('p', { className: 'seed' }, el('label', { htmlFor: 'seed', textContent: 'Replay seed ' }), seedInput,
      ' the same seed lays out the same arena for every generation; the first watch of each records it (a second or two)'),
    gens.el,
    el('h2', { textContent: 'Training' }),
    ...body,
    ...behind(d.compute));
  setStatus('ok');
  log.debug('run shown', { id, updates: d.metrics.length, checkpoints: d.checkpoints.length, state: d.state });
  if (d.state === 'live') setTimeout(() => ticket === showing && void refresh(), POLL_MS);
}

async function refresh() {
  const ticket = showing;
  const id = decodeURIComponent(location.hash.slice(1));
  try {
    await (id ? showRun(id, ticket) : showList(ticket));
  } catch (err) {
    if (ticket !== showing) return;
    log.error('runs failed to load', { id, err });
    setStatus('error', err instanceof ServerError ? `Couldn’t load ${id ? 'that run' : 'the runs'}: ${err.message}.` : `Something broke: ${String(err)}`);
  }
}

function navigate() {
  showing++;
  if (!main.childElementCount) setStatus('loading', 'Loading runs…');
  void refresh();
}

window.addEventListener('hashchange', navigate);
window.addEventListener('error', (e) => log.error('uncaught error', e.error ?? e.message));
window.addEventListener('unhandledrejection', (e) => log.error('unhandled rejection', e.reason));
if (import.meta.env.DEV) import('./devlog').then((m) => m.mountLogViewer());
navigate();
