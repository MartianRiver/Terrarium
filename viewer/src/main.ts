import { createDemo } from './demo';
import { createLogger } from './lib/logger';
import { createStage } from './stage';
import { WorldView } from './worldview';

const log = createLogger('main');

const status = document.getElementById('status')!;

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
  const demo = createDemo();
  const stage = createStage(container, demo.info);
  const view = new WorldView(stage.scene, demo.info);

  stage.renderer.domElement.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    log.error('webgl context lost');
    setStatus('error', 'Lost the graphics context. Reload to try again.');
  });

  const tickSeconds = 1 / demo.info.tickHz;
  let paused = false;
  let acc = 0;
  let last = performance.now();
  view.push(demo.step());

  window.addEventListener('keydown', (e) => {
    if (e.key !== 'p' && e.key !== 'P') return;
    paused = !paused;
    log.info(paused ? 'paused' : 'resumed');
  });

  function frame(now: number) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (!paused) {
      acc += dt;
      while (acc >= tickSeconds) {
        view.push(demo.step());
        acc -= tickSeconds;
      }
    }
    view.render(acc / tickSeconds, paused ? 0 : dt, now / 1000);
    stage.render();

    if (view.creatureCount === 0) setStatus('empty', 'No creatures in this world.');
    else if (status.dataset.kind !== 'ok' && status.dataset.kind !== 'error') setStatus('ok');
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  log.info('running', { tickHz: demo.info.tickHz });
}

try {
  boot();
} catch (err) {
  log.error('boot failed', err);
  setStatus('error', `Something broke while starting up: ${err instanceof Error ? err.message : String(err)}`);
}
