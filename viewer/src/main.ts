import { createDemo } from './demo';
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

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

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

  const container = document.getElementById('world')!;
  const stage = createStage(container);
  let make = demoSource;
  let source!: Source;
  let view: WorldView | undefined;
  let paused = false;
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
    view = new WorldView(stage.scene, source.info);
    view.push(source.step()!);
    acc = 0;
  }

  async function open(file: File) {
    opening = true;
    setStatus('loading', `Reading ${file.name}…`);
    try {
      const replay = await readReplay(new Uint8Array(await file.arrayBuffer()));
      log.info('replay opened', { name: file.name, version: replay.version, frames: replay.frames.length, source: replay.source.commit });
      make = () => replaySource(replay, file.name);
      restart(true);
      setStatus('ok');
    } catch (err) {
      log.error('replay failed to open', { name: file.name, err });
      const why = err instanceof ReplayError ? err.message : `something broke (${String(err)})`;
      setStatus('error', `Couldn’t open ${file.name}: ${why}. Click or press Esc to close this.`);
    } finally {
      opening = false;
    }
  }

  openButton.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    fileInput.value = '';
    if (file) void open(file);
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files[0];
    if (file) void open(file);
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
  });

  restart(true);

  function frame(now: number) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const tickSeconds = 1 / source.info.tickHz;
    if (!paused) {
      acc += dt;
      while (acc >= tickSeconds) {
        const next = source.step();
        if (!next) {
          restart();
          break;
        }
        view!.push(next);
        acc -= tickSeconds;
      }
    }
    view!.render(acc / tickSeconds, paused ? 0 : dt, now / 1000);
    stage.render();

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
