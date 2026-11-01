import * as THREE from 'three';
import { AntStudy } from './ant';
import { BrainView } from './brainview';
import { ChannelCard, type Game as ChannelGame, type Item } from './channelcard';
import { Picker } from './picker';
import { clock } from './clock';
import { Cues } from './cues';
import { createDemo } from './demo';
import { Director } from './director';
import { galleryBar } from './gallery';
import { LearnsBar } from './learns';
import { createLogger } from './lib/logger';
import { namesFor } from './names';
import { Game } from './play';
import { withNectar } from './preview';
import { readReplay, ReplayError, type Replay } from './replay';
import { Sounds } from './sounds';
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
  // a live source (a game) can be waiting on its next frames; a replay always has one
  ready?(): boolean;
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

// the garden with nobody in it, while the site asks what to watch
function emptySource(): Source {
  const { info } = createDemo();
  let tick = 0;
  return {
    info: { ...info, nests: [] },
    step: () => ({ tick: tick++, creatures: [], food: [], blocks: [], stores: [], light: 1, eggs: [], flowers: [], flags: [] }),
    label: () => 'choosing what to watch',
  };
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
  // &turn=degrees: the close-up from another side (a reel's shot of a face)
  const stage = createStage(container, lite, (Number(params.get('turn')) || 0) * Math.PI / 180);
  // the site with nothing asked for opens on an empty garden and asks what to watch; with something asked for, the
  // garden stays empty until it comes
  const choosing = SITE && !location.search;
  // the site plays only with an invite to the hosted play server (?play&invite=…)
  const hosted = SITE && params.has('play') && params.has('invite');
  let make = SITE ? emptySource : demoSource;
  let source!: Source;
  let view: WorldView | undefined;
  let paused = false;
  // the camera: the whole arena (wide), close behind the Terrikin that matters most (follow), or cutting between the
  // shots that matter like a match on TV (action); &cam= picks one, &follow is follow
  type Cam = 'wide' | 'follow' | 'action';
  const CAMS: Cam[] = ['wide', 'follow', 'action'];
  const CAM_WORDS: Record<Cam, string> = { wide: 'Wide', follow: 'Follow', action: 'Action' };
  let cam: Cam = 'wide';
  // &intro circles outside the dome until the first camera change
  let intro = false;
  // the Terrikin picked by clicking it (or by &pick), kept across restarts; null follows the first one
  let chosen: number | null = params.has('pick') ? Number(params.get('pick')) : null;
  // &look=x,y,heading: the close-up held on one spot instead of a Terrikin (a reel's shot of a nest)
  const [lx, ly, lh] = (params.get('look') ?? '').split(',').map(Number);
  const look = params.has('look') ? { x: lx, y: ly, heading: lh || 0 } : null;
  let nameOf = namesFor('demo');
  // ?play: you're one of the Terrikins (play.ts)
  let game: Game | null = null;
  // the picked Terrikin's name, above it
  const tag = document.createElement('div');
  tag.className = 'nametag';
  tag.hidden = true;
  document.body.append(tag);
  const above = new THREE.Vector3();
  let tick = 0;
  // the brain window (B): local only, it reads brains through the runs server
  const brain = SITE ? null : new BrainView(document.body, stage.scene, (url) => void open(`${url.pathname.split('/').pop()} (recorded here)`, () => fetchReplay(url), url));
  // chips for the same brain from random moves to now (learns.ts): a run's replay here, a channel item's stages
  const learns = new LearnsBar((url, label) => void open(label, () => fetchReplay(url), url), params.has('learns'));
  // after a restart the camera jumps to the blob rather than sweeping across the arena after it
  let snap = true;
  // in a nursery game, who to follow and where the action is (&solo turns it off)
  const director = params.has('solo') ? null : new Director();
  let opening = false;
  let acc = 0;
  let last = performance.now();
  const cues = new Cues();
  const sounds = new Sounds(stage.camera);

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
    // &cone=<degrees>: tag's it shows how much it can see, as a fan on the ground (for reels)
    view = new WorldView(stage.scene, source.info, !params.has('nodroppings'), Number(params.get('cone') ?? 0));
    view.chosen = chosen;
    view.marked = !params.has('pick');
    director?.reset();
    const first = source.step()!;
    view.push(first);
    cues.reset(source.info.nests);
    cues.next(first);
    tick = first.tick;
    stage.light(first.light);
    sounds.light(first.light, true);
    acc = 0;
    snap = true;
  }

  const camButton = document.createElement('button');
  camButton.type = 'button';
  camButton.addEventListener('click', () => setCam(CAMS[(CAMS.indexOf(cam) + 1) % CAMS.length]));
  function setCam(next: Cam) {
    cam = next;
    intro = false;
    stage.release();
    if (cam !== 'wide') stage.view(true);
    const after = CAMS[(CAMS.indexOf(cam) + 1) % CAMS.length];
    camButton.textContent = CAM_WORDS[cam];
    camButton.setAttribute('aria-label', `Camera: ${CAM_WORDS[cam]}. Switch to ${CAM_WORDS[after]}`);
    log.info('camera', { cam });
  }

  // url: where it came from, if it was fetched
  async function open(name: string, read: () => Promise<ArrayBuffer>, url: URL | null = null) {
    opening = true;
    setStatus('loading', `Reading ${name}…`);
    try {
      const replay = await readReplay(new Uint8Array(await read()));
      log.info('replay opened', { name, version: replay.version, frames: replay.frames.length, source: replay.source.commit });
      // &preview lays make-believe nectar flowers and sprints over the replay (preview.ts)
      make = () => {
        const src = replaySource(replay, name);
        return params.has('preview') ? { ...src, step: withNectar(src.info, src.step) } : src;
      };
      // opening another episode drops the pick; the page's first one keeps &pick
      const first = !playing;
      if (newReplay(url) && !first) chosen = null;
      // a run's replay recorded again here is the same episode, so it keeps its names
      const run = url && /^\/api\/runs\//.test(url.pathname) ? `${url.pathname}?${url.searchParams.get('seed')}` : null;
      const brainId = (replay.source.brain as { id?: string } | undefined)?.id ?? String(replay.source.brain);
      nameOf = namesFor(run ?? `${brainId}/${replay.source.seed}`);
      brain?.playingNow(url, replay.frames);
      if (brain) brain.name = nameOf;
      restart(true);
      void learns.show(url);
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

  // a game in the world of ?play=<run id> (or the newest live run) against its newest brain, you the ringed one
  async function play() {
    opening = true;
    setStatus('loading', 'Starting a game…');
    try {
      const next = await Game.begin(params.get('play') || null, stage.camera, stage.renderer.domElement, params.get('invite'));
      game?.end();
      game = next;
      make = () => next;
      chosen = next.you;
      nameOf = namesFor(`play/${next.token}`);
      stage.lookWithRight();
      restart(true);
      setCam('follow');
      const hint = document.querySelector('#hud .hint');
      if (hint) hint.textContent = 'you have the ring · the keys are in the panel';
      log.info('game started', { you: next.you });
      setStatus('ok');
    } catch (err) {
      log.error('game failed to start', { err });
      setStatus('error', `Couldn’t start a game: ${err instanceof Error ? err.message : String(err)}. Click or press Esc to close this.`);
    } finally {
      opening = false;
    }
  }
  // ids only name the same Terrikins in the same episode: a run's replay recorded again here is that
  let playing = '';
  function newReplay(url: URL | null) {
    const same = url ? `${url.pathname}?seed=${url.searchParams.get('seed')}` : '';
    const changed = !same || same !== playing;
    playing = same;
    return changed;
  }

  // a click (not a drag) on a Terrikin follows it
  const pointer = { x: 0, y: 0, at: 0 };
  const caster = new THREE.Raycaster();
  stage.renderer.domElement.addEventListener('pointerdown', (e) => Object.assign(pointer, { x: e.clientX, y: e.clientY, at: performance.now() }));
  stage.renderer.domElement.addEventListener('pointerup', (e) => {
    if (!view || game || Math.hypot(e.clientX - pointer.x, e.clientY - pointer.y) > 6 || performance.now() - pointer.at > 400) return;
    const box = stage.renderer.domElement.getBoundingClientRect();
    caster.setFromCamera(new THREE.Vector2(((e.clientX - box.left) / box.width) * 2 - 1, -((e.clientY - box.top) / box.height) * 2 + 1), stage.camera);
    const id = view.pick(caster);
    if (id === null) return;
    chosen = view.chosen = id;
    log.info('following a Terrikin', { id });
    if (cam !== 'follow') setCam('follow');
  });

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
      await open(`${run.id.replace(/^\d{8}-\d{6}-/, '')} · ${(newest.samples / 1e6).toFixed(1)}M`, async () => bytes,
        new URL(`/api/runs/${run.id}/replay/${newest.file}?seed=0`, location.href));
    } catch (err) {
      log.warn('latest checkpoint not opened', { err: String(err) });
    } finally {
      looking = false;
      // nothing to loop yet (the demo never runs out), so keep looking
      if (!latest) setTimeout(openLatest, 30_000);
    }
  }

  // ?channel=<index.json>[&game=<key>]: its replays in turn, each with its title as the label; the list is read again each time
  // one runs out, so replays added while training (newer checkpoints) come round on the next pass
  let showing = '';
  let tuning = false;
  const card = new ChannelCard(document.body);
  async function openChannel() {
    if (tuning) return;
    tuning = true;
    if (!showing) {
      opening = true;
      setStatus('loading', 'Reading the channel…');
    }
    try {
      const index = new URL(params.get('channel')!, location.href);
      if (index.origin !== location.origin) throw new ReplayError(`won’t read a channel from another site (${index.origin})`);
      const read: { items: Item[]; games?: Record<string, ChannelGame>; note?: string } = await (await fetch(index, { cache: 'no-cache' })).json();
      const { games = {}, note } = read;
      // &game=<key>[,<key>…] keeps to those games' replays
      const game = params.get('game')?.split(',');
      const items = game ? read.items.filter((i) => game.includes(i.game ?? '')) : read.items;
      if (!items.length) throw new ReplayError('nothing on the channel yet');
      const place = (items.findIndex((i) => i.replay === showing) + 1) % items.length;
      const item = items[place];
      const url = new URL(item.replay, index);
      if (url.origin !== location.origin) throw new ReplayError(`won’t fetch a replay from another site (${url.origin})`);
      const bytes = await fetchReplay(url);
      showing = item.replay;
      await open(item.title, async () => bytes, url);
      card.show(item, games, place, items.length, note);
      if (item.stages?.length) learns.set(item.stages.map((s) => ({ label: s.label, url: new URL(s.replay, index), aria: s.about ?? s.label })), url, item.title);
    } catch (err) {
      log.warn('channel not read', { err: String(err) });
      if (!showing) setStatus('loading', 'The channel isn’t answering. Trying again in 30 s…');
    } finally {
      tuning = false;
      if (!showing) setTimeout(openChannel, 30_000);
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
    if (e.key === 'Escape') {
      dismiss();
      chosen = null;
      if (view) view.chosen = null;
    }
    if (brain && (e.key === 'b' || e.key === 'B')) brain.toggle();
    if (brain && (e.key === 'n' || e.key === 'N')) brain.toggleNet();
    if (e.key === 'r' || e.key === 'R') {
      if (game) void play();
      else restart();
      log.info('restarted');
    }
    if (e.key === 'p' || e.key === 'P') {
      paused = !paused;
      log.info(paused ? 'paused' : 'resumed');
    }
    if (e.key === 'v' || e.key === 'V') setCam(intro ? 'follow' : CAMS[(CAMS.indexOf(cam) + 1) % CAMS.length]);
    if (e.key === 'f' || e.key === 'F') setCam('follow');
    if (e.key === 'm' || e.key === 'M') void sounds.toggle();
    if (ant && (e.key === 'j' || e.key === 'J')) ant.marked = !ant.marked;
  });

  restart(true);
  // &ant: a sketch of a walking ant beside whatever is playing; F follows it
  const ant = params.has('ant') ? new AntStudy(stage.scene) : null;
  if (params.has('intro')) stage.intro();
  const asked = params.get('cam') as Cam | null;
  setCam(asked && CAMS.includes(asked) ? asked : params.has('follow') ? 'follow' : 'wide');
  intro = params.has('intro');
  openButton.before(camButton, ' ', sounds.button, ' ', sounds.musicButton, ' ');
  document.querySelector('#hud .hint')?.append(' · M sound');
  // the public site has no runs page; the link goes back to the front page instead
  const runsLink = document.querySelector<HTMLAnchorElement>('a[href="/runs.html"]');
  if (SITE && runsLink) {
    runsLink.href = '/';
    runsLink.textContent = 'About';
  }
  // on the site, other replays are picked from the gallery; a file picker means nothing on a phone (dropping one still works)
  if (brain) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Brain';
    button.addEventListener('click', () => brain.toggle());
    openButton.after(' ', button);
    document.querySelector('#hud .hint')?.append(' · B brain · N wired up');
  }
  if (SITE) {
    const brains = document.createElement('a');
    brains.href = '/brains/';
    brains.textContent = 'Brains';
    // closing it without a pick plays the newest replay
    const picker = new Picker(document.body, () => {
      if (choosing && !playing) void open('the newest replay', () => fetchReplay(new URL(SITE_REPLAY, location.href)), new URL(SITE_REPLAY, location.href));
    });
    const choose = document.createElement('button');
    choose.textContent = 'Choose';
    choose.setAttribute('aria-label', 'Choose what to watch');
    choose.addEventListener('click', () => void picker.open());
    openButton.replaceWith(choose, ' ', brains);
    // nothing asked for: say what there is, over the garden playing behind
    if (!location.search) void picker.open();
  }
  const channel = params.has('channel');
  const wanted = params.get('replay') ?? (SITE && !channel && !choosing && !hosted ? SITE_REPLAY : null);
  if (wanted) {
    const url = new URL(wanted, location.href);
    const name = params.get('name') ?? url.pathname.split('/').pop()!;
    if (url.origin === location.origin) void open(name, () => fetchReplay(url), url);
    else setStatus('error', `Won’t fetch a replay from another site (${url.origin}). Click or press Esc to close this.`);
  }
  const place = Number(params.get('gallery'));
  if (params.has('gallery') && Number.isInteger(place)) void galleryBar(place);
  if (!SITE) {
    const link = document.createElement('a');
    link.href = '/?play';
    link.textContent = 'Play';
    document.querySelector('a[href="/runs.html"]')?.after(' ', link);
  }
  if ((!SITE && params.has('play')) || hosted) void play();
  const watching = !SITE && params.has('latest');
  if (watching) void openLatest();
  if (channel) void openChannel();

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
        if (source.ready && !source.ready()) {
          acc = Math.min(acc, tickSeconds);
          break;
        }
        const next = source.step();
        if (!next) {
          restart();
          learns.ended();
          if (watching) void openLatest();
          if (channel) void openChannel();
          break;
        }
        view!.push(next);
        if (channel) card.frame(next);
        tick = next.tick;
        stage.light(next.light);
        sounds.light(next.light);
        sounds.hear(cues.next(next));
        acc -= tickSeconds;
      }
    }
    view!.render(acc / tickSeconds, paused ? 0 : dt, now / 1000);
    ant?.update(paused ? 0 : dt);
    brain?.frame(view!.focusId, view!.focus, tick);
    tag.hidden = chosen === null || !view!.focus;
    if (!tag.hidden) {
      const f = view!.focus!;
      above.set(f.x, 1.3, f.y).project(stage.camera);
      tag.style.transform = `translate(${((above.x + 1) / 2) * innerWidth}px, ${((1 - above.y) / 2) * innerHeight}px) translate(-50%, -100%)`;
      if (tag.textContent !== nameOf(chosen!)) tag.textContent = nameOf(chosen!);
    }
    const step = snap ? Infinity : paused ? 0 : dt;
    const scripted = look || ant || game;
    const shot = !scripted && view!.current ? director?.shot(view!.current, paused ? 0 : dt) : null;
    view!.lead = director?.lead ?? null;
    if (intro) stage.track(null, step);
    else if (cam === 'action' && shot && chosen === null && !scripted) stage.aim(shot, step);
    else if (cam === 'wide' && !scripted) stage.wide(step);
    else stage.track(ant?.focus ?? look ?? view!.focus, step);
    snap = false;
    stage.render(now / 1000);

    const label = source.label();
    if (sourceLabel.textContent !== label) sourceLabel.textContent = label;
    const want = view!.creatureCount ? 'ok' : 'empty';
    if (!opening && status.dataset.kind !== 'error' && status.dataset.kind !== want && make !== emptySource) setStatus(want, 'No creatures in this world.');
    if (make === emptySource && status.dataset.kind === 'loading' && !opening) setStatus('ok');
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
