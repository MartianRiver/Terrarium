// Renders reel clips from the viewer page on a fake clock (30 fps, any playback speed), with text
// labels, a replay clock and keypresses at set replay times. Each frame is POSTed to receive.py.
// In the page a clip's url opens: (await import('/reel/harness.js')).run('/reel/0.2.json', '02-rules')
const FPS = 30;
const RECEIVER = 'http://127.0.0.1:8799';
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

// Geist on cream boxes (River picked it from sheets of five looks, 2026-10-23)
const FONTS = 'https://fonts.googleapis.com/css2?family=Geist:wght@400..800&display=swap';
const HEAD = ["'Geist'", 700, 64];
const SUB = ["'Geist'", 500, 42];
const INK = '#23301c';
const BOX = '#fff4df';
const SUB_BOX = 'rgba(255, 244, 223, 0.82)';

async function loadFonts() {
  if (!document.querySelector(`link[href="${FONTS}"]`)) {
    const link = Object.assign(document.createElement('link'), { rel: 'stylesheet', href: FONTS });
    const loaded = new Promise((ok, fail) => ((link.onload = ok), (link.onerror = fail)));
    document.head.append(link);
    await loaded;
  }
  // fonts.check() is true for families with no @font-face at all, so look for the loaded faces
  for (const [font, weight] of [HEAD, SUB]) {
    await document.fonts.load(`${weight} 40px ${font}`);
    const family = font.replaceAll("'", '');
    if (![...document.fonts].some((f) => f.family.replaceAll('"', '') === family && f.status === 'loaded')) {
      throw new Error(`font not loaded: ${family}`);
    }
  }
}

const bytesOf = (canvas, type = 'image/jpeg') =>
  Uint8Array.from(atob(canvas.toDataURL(type, 0.92).split(',')[1]), (c) => c.charCodeAt(0));

// shrinks to fit within fit px (Instagram wants 6% clear at each side)
function text(ctx, s, x, y, [font, weight, size], fit, box) {
  ctx.font = `${weight} ${size}px ${font}`;
  const width = ctx.measureText(s).width;
  if (width > fit) {
    size = Math.floor((size * fit) / width);
    ctx.font = `${weight} ${size}px ${font}`;
  }
  const w = ctx.measureText(s).width + size * 0.8;
  const left = ctx.textAlign === 'center' ? x - w / 2 : x - size * 0.4;
  ctx.fillStyle = box;
  ctx.beginPath();
  ctx.roundRect(left, y - size * 0.98, w, size * 1.32, size * 0.3);
  ctx.fill();
  ctx.fillStyle = INK;
  ctx.fillText(s, x, y);
}

// first line big, the rest smaller; starts below Instagram's top 14%
function lines(ctx, list, w, y = 360) {
  ctx.textAlign = 'center';
  list.forEach((s, i) => {
    if (i === 0) {
      text(ctx, s, w / 2, y, HEAD, w * 0.86, BOX);
      y += HEAD[2] * 0.98;
    } else {
      text(ctx, s, w / 2, y, SUB, w * 0.86, SUB_BOX);
      y += SUB[2] * 1.5;
    }
  });
}

function pill(ctx, s, w, y) {
  ctx.font = `600 44px ${SUB[0]}`;
  const width = ctx.measureText(s).width + 56;
  ctx.fillStyle = BOX;
  ctx.beginPath();
  ctx.roundRect((w - width) / 2, y - 46, width, 66, 33);
  ctx.fill();
  ctx.textAlign = 'center';
  ctx.fillStyle = INK;
  ctx.fillText(s, w / 2, y);
}

// sizes the 3D view to the clip and takes over requestAnimationFrame, so frames only advance on step()
async function setup(size, demo) {
  const label = document.getElementById('source');
  if (!demo) while (!label.textContent.includes('/')) await pause(100);
  const world = document.getElementById('world');
  const ratio = Math.min(devicePixelRatio, 2);
  Object.assign(world.style, { position: 'fixed', left: '0', top: '0', width: `${size[0] / ratio}px`, height: `${size[1] / ratio}px` });
  dispatchEvent(new Event('resize'));
  const gl = world.querySelector('canvas');
  if (gl.width !== size[0] || gl.height !== size[1]) throw new Error(`canvas is ${gl.width}x${gl.height}`);
  let queued = null;
  window.requestAnimationFrame = (cb) => ((queued = cb), 1);
  while (!queued) await pause(20);
  let now = performance.now();
  const step = (ms) => {
    now += ms;
    const cb = queued;
    queued = null;
    cb(now);
  };
  return { gl, label, step };
}

// shots: [{from, to, speed}] and labels: [{from, to, lines}] in replay seconds; keys: [{at, key}];
// hold: seconds to keep the last frame, showing end on the clock (the replay clock rounds down);
// tag: a small label in a grid cell; demo: the scripted demo rather than a replay
export async function clip({ name, shots, labels = [], keys = [], hold = 0, end, clock = false, size = [1080, 1920], tag, demo = false }) {
  const [W, H] = size;
  await loadFonts();
  const { gl, label, step } = await setup(size, demo);
  dispatchEvent(new KeyboardEvent('keydown', { key: 'r' }));
  step(0);
  let t = 0;
  const pending = [...keys];
  // main.ts clamps a frame's dt at 0.1 s, so seek in 100 ms steps
  const advance = (seconds) => {
    let left = seconds * 1000;
    while (left > 1e-6) {
      const ms = Math.min(100, left);
      step(ms);
      left -= ms;
      t += ms / 1000;
      while (pending.length && pending[0].at <= t) dispatchEvent(new KeyboardEvent('keydown', { key: pending.shift().key }));
    }
  };
  const out = Object.assign(document.createElement('canvas'), { width: W, height: H });
  const ctx = out.getContext('2d');
  // the WebGL canvas reads blank outside its frame, so it's copied straight after each step
  const base = Object.assign(document.createElement('canvas'), { width: W, height: H });
  let n = 0;
  const post = (jpeg) => fetch(`${RECEIVER}/frame/${name}/${n++}`, { method: 'POST', body: jpeg });
  const compose = (time) => {
    ctx.drawImage(base, 0, 0);
    const on = labels.find((l) => t >= (l.from ?? 0) && t < (l.to ?? Infinity));
    if (on) lines(ctx, on.lines, W);
    if (clock) pill(ctx, time, W, 1200);
    if (tag) {
      ctx.textAlign = 'left';
      text(ctx, tag, 22, 50, [HEAD[0], 700, 34], Infinity, BOX);
    }
    return bytesOf(out);
  };
  const replayClock = () => label.textContent.match(/(\d+:\d\d) \//)?.[1] ?? '';
  for (const shot of shots) {
    if (t < shot.from) advance(shot.from - t);
    const frames = Math.floor(((shot.to - shot.from) / shot.speed) * FPS);
    for (let f = 0; f < frames; f++) {
      advance(shot.speed / FPS);
      base.getContext('2d').drawImage(gl, 0, 0, W, H);
      await post(compose(shot.speed === 1 ? replayClock() : `${replayClock()} · ${shot.speed}× speed`));
    }
  }
  if (hold) {
    const jpeg = compose(end ?? replayClock());
    for (let f = 0; f < Math.round(hold * FPS); f++) await post(jpeg);
  }
  return `${name}: ${n} frames, ended at ${label.textContent} (t ${t.toFixed(2)})`;
}

// text on a transparent 1080x1920 png, laid over a grid by build.py
export async function card({ name, lines: list, y = 360 }) {
  await loadFonts();
  const out = Object.assign(document.createElement('canvas'), { width: 1080, height: 1920 });
  lines(out.getContext('2d'), list, 1080, y);
  await fetch(`${RECEIVER}/card/${name}`, { method: 'POST', body: bytesOf(out, 'image/png') });
  return `${name}: card`;
}

// renders one clip or card of a reel script; a clip must be run on its own url
export async function run(script, name) {
  const reel = await (await fetch(script, { cache: 'no-cache' })).json();
  const c = reel.cards.find((x) => x.name === name);
  if (c) return card(c);
  const entry = reel.clips.find((x) => x.name === name);
  if (!entry) throw new Error(`${name} isn't in ${script}`);
  if (location.pathname + location.search !== entry.url) throw new Error(`${name} needs ${entry.url}`);
  return clip({ name, ...entry.clip });
}
