import { clock } from './clock';
import { createDemo } from './demo';
import { galleryBar } from './gallery';
import { createLogger } from './lib/logger';
import { readReplay, ReplayError, type Replay } from './replay';
import { createStage } from './stage';
import type { Frame, WorldInfo } from './world';
import { WorldView } from './worldview';

const log = createLogger('main');

const status = document.getElementById('status')!;
const sourceLabel = document.getElementById('source')!;
const openButton = document.getElementById('open')!;
const fileInput = document.getElementById('file') as HTMLInputElement;

// anything that hands out a Frame per tick; step() returns null when it has run out
interface Source {
  info: WorldInfo;
  step(): Frame | null;
  label(): string;
}

function setStatus(kind: 'loading' | 'empty' | 'error' | 'ok', text = '') {
  status.dataset.kind = kind;
  status.textContent = text;
  status.hidden = kind === 'ok';
}

function webglAvailable() {
  try {
    return !!document.createElement('canvas').getContext('webgl2');
  } catch {
    return false;
  }
}

// the public site (`npm run site`) opens the newest replay instead of the scripted demo,
// and has no runs page (that needs terrarium.serve)
const SITE = import.meta.env.MODE === 'site';
const SITE_REPLAY = '/replays/latest.jsonl.gz';


function demoSource(): Source {
  return { ...createDemo(), label: () => 'scripted demo' };
}

function replaySource(replay: Replay, name: string): Source {
  const hz = replay.info.tickHz;
  const length = clock((replay.frames.length - 1) / hz);
  let i = 0;
  return {
    info: replay.info,
    step: () => replay.frames[i++] ?? null,
    label: () => `${name} · ${clock(Math.max(0, i - 1) / hz)} / ${length}`,
  };
}

window.addEventListener('error', (e) => log.error('uncaught error', e.error ?? e.message));
window.addEventListener('unhandledrejection', (e) => log.error('unhandled rejection', e.reason));

if (import.meta.env.DEV) import('./devlog').then((m) => m.mountLogViewer());

function boot() {
  setStatus('loading', 'Waking the blobs…');
  if (!webglAvailable()) {
    log.error('webgl2 unavailable');
    setStatus('error', 'This browser can’t do WebGL2, so the world can’t be drawn.');
    return;
  }

  const params = new URLSearchParams(location.search);
  const lite = params.has('lite');
  const container = document.getElementById('world')!;
  const stage = createStage(container, lite);
  let make = demoSource;
  let source!: Source;
  let view: WorldView | undefined;
  let paused = false;
  let following = false;
  // after a restart the camera jumps to the blob rather than sweeping across the arena after it
  let snap = true;
  let opening = false;
  let acc = 0;
  let last = performance.now();

  stage.renderer.domElement.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    log.error('webgl context lost');
    setStatus('error', 'Lost the graphics context. Reload to try again.');
  });

  // from the top: a replay that has run out loops, and R does the same by hand
  function restart(newWorld = false) {
    view?.dispose();
    source = make();
    if (newWorld) stage.setWorld(source.info);
    view = new WorldView(stage.scene, source.info, !params.has('nodroppings'));
    const first = source.step()!;
    view.push(first);
    stage.light(first.light);
    acc = 0;
    snap = true;
  }

  function follow(on: boolean) {
    following = on;
    stage.view(on);
    log.info(on ? 'following' : 'overview');
  }

  async function open(name: string, read: () => Promise<ArrayBuffer>) {
    opening = true;
    setStatus('loading', `Reading ${name}…`);
    try {
      const replay = await readReplay(new Uint8Array(await read()));
      log.info('replay opened', { name, version: replay.version, frames: replay.frames.length, source: replay.source.commit });
      make = () => replaySource(replay, name);
      restart(true);
      setStatus('ok');
    } catch (err) {
      log.error('replay failed to open', { name, err });
      const why = err instanceof ReplayError ? err.message : `something broke (${String(err)})`;
      setStatus('error', `Couldn’t open ${name}: ${why}. Click or press Esc to close this.`);
    } finally {
      opening = false;
    }
  }
  const openFile = (file: File) => open(file.name, () => file.arrayBuffer());

  // ?replay=/api/runs/<id>/replay/<checkpoint> from the runs page; only this server's own urls
  async function fetchReplay(url: URL) {
    // Cloudflare has browsers keep replays for hours; revalidate so a new latest shows up
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ReplayError(body?.error ?? `the server said ${res.status}`);
    }
    return res.arrayBuffer();
  }

  // ?latest[=text]: the newest checkpoint of the newest run whose id has text in it, or with no text, of each
  // live run in turn; looked for again each time the replay runs out, and the old one loops while the next records
  let latest = '';
  let looking = false;
  async function openLatest() {
    if (looking) return;
    looking = true;
    try {
      const want = params.get('latest') ?? '';
      const runs: { id: string; state: string }[] = await (await fetch('/api/runs', { cache: 'no-cache' })).json();
      const live = runs.filter((r) => r.state === 'live');
      const pool = want ? runs.filter((r) => r.id.includes(want)).slice(0, 1) : live.length ? live : runs.slice(0, 1);
      const run = pool[(pool.findIndex((r) => latest.startsWith(`${r.id}/`)) + 1) % pool.length];
      if (!run) throw new ReplayError(`no run matching “${want}”`);
      const detail: { checkpoints: { file: string; samples: number }[] } = await (await fetch(`/api/runs/${run.id}`, { cache: 'no-cache' })).json();
      const newest = detail.checkpoints.at(-1);
      if (!newest || `${run.id}/${newest.file}` === latest) return;
      const bytes = await fetchReplay(new URL(`/api/runs/${run.id}/replay/${newest.file}?seed=0`, location.href));
      latest = `${run.id}/${newest.file}`;
      log.info('newer checkpoint', { run: run.id, samples: newest.samples });
      await open(`${run.id.replace(/^\d{8}-\d{6}-/, '')} · ${(newest.samples / 1e6).toFixed(1)}M`, async () => bytes);
    } catch (err) {
      log.warn('latest checkpoint not opened', { err: String(err) });
    } finally {
      looking = false;
      // nothing to loop yet (the demo never runs out), so keep looking
      if (!latest) setTimeout(openLatest, 30_000);
    }
  }

  openButton.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    fileInput.value = '';
    if (file) void openFile(file);
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files[0];
    if (file) void openFile(file);
  });

  const dismiss = () => status.dataset.kind === 'error' && view && setStatus('ok');
  status.addEventListener('click', dismiss);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') dismiss();
    if (e.key === 'r' || e.key === 'R') {
      restart();
      log.info('restarted');
    }
    if (e.key === 'p' || e.key === 'P') {
      paused = !paused;
      log.info(paused ? 'paused' : 'resumed');
    }
    if (e.key === 'f' || e.key === 'F') follow(!following);
  });

  restart(true);
  if (params.has('intro')) stage.intro();
  if (params.has('follow')) follow(true);
  // the public site has no runs page; the link goes back to the front page instead
  const runsLink = document.querySelector<HTMLAnchorElement>('a[href="/runs.html"]');
  if (SITE && runsLink) {
    runsLink.href = '/';
    runsLink.textContent = 'About';
  }
  // on the site, other replays are picked from the gallery; a file picker means nothing on a phone (dropping one still works)
  if (SITE) {
    const brains = document.createElement('a');
    brains.href = '/brains/';
    brains.textContent = 'Brains';
    openButton.replaceWith(brains);
  }
  const wanted = params.get('replay') ?? (SITE ? SITE_REPLAY : null);
  if (wanted) {
    const url = new URL(wanted, location.href);
    const name = params.get('name') ?? url.pathname.split('/').pop()!;
    if (url.origin === location.origin) void open(name, () => fetchReplay(url));
    else setStatus('error', `Won’t fetch a replay from another site (${url.origin}). Click or press Esc to close this.`);
  }
  const place = Number(params.get('gallery'));
  if (params.has('gallery') && Number.isInteger(place)) void galleryBar(place);
  const watching = !SITE && params.has('latest');
  if (watching) void openLatest();

  // lite draws 30 frames a second at most
  const gap = lite ? 1000 / 30 - 2 : 0;
  function frame(now: number) {
    if (now - last < gap) {
      requestAnimationFrame(frame);
      return;
    }
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const tickSeconds = 1 / source.info.tickHz;
    if (!paused) {
      acc += dt;
      while (acc >= tickSeconds) {
        const next = source.step();
        if (!next) {
          restart();
          if (watching) void openLatest();
          break;
        }
        view!.push(next);
        stage.light(next.light);
        acc -= tickSeconds;
      }
    }
    view!.render(acc / tickSeconds, paused ? 0 : dt, now / 1000);
    stage.track(following ? view!.focus : null, snap ? Infinity : paused ? 0 : dt);
    snap = false;
    stage.render(now / 1000);

    const label = source.label();
    if (sourceLabel.textContent !== label) sourceLabel.textContent = label;
    const want = view!.creatureCount ? 'ok' : 'empty';
    if (!opening && status.dataset.kind !== 'error' && status.dataset.kind !== want) setStatus(want, 'No creatures in this world.');
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  log.info('running', { tickHz: source.info.tickHz });
}

try {
  boot();
} catch (err) {
  log.error('boot failed', err);
  setStatus('error', `Something broke while starting up: ${err instanceof Error ? err.message : String(err)}`);
}
