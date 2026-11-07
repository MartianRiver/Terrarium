// Renders reel clips from the viewer page on a fake clock (30 fps, any playback speed), with text
// labels, a replay clock and keypresses at set replay times. Each frame is POSTed to receive.py.
// In the page a clip's url opens: (await import('/reel/harness.js')).run('/reel/0.2.json', '02-rules')
const FPS = 30;
const RECEIVER = `http://127.0.0.1:${new URLSearchParams(location.search).get('receiver') ?? 8799}`;
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

// first line big, the rest smaller; starts below Instagram's top 14%; returns the y below the last line
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
  return y;
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

// the followed nim's senses card (src/vitals.ts) drawn on the clip: the page's card is DOM, which a clip never
// holds, so this paints window.terrariumVitals.model() the same way. o: {scale, x, y} (px); the defaults are
// landscape top left and portrait low, below the labels and clear of Instagram's bottom 20%
function vitalsCard(ctx, model, W, H, o = {}) {
  if (!model) return;
  const u = 13 * (o.scale ?? (W >= H ? 1.7 : 2.0));
  const width = u * 19;
  const pad = u * 0.95;
  const valueX = pad + u * 4.6;
  const font = (weight, size = u) => `${weight} ${size}px 'Geist'`;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  const wrap = (s, max) => {
    const out = [];
    let line = '';
    for (const word of s.split(' ')) {
      const next = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(next).width > max) (out.push(line), (line = word));
      else line = next;
    }
    return out.concat(line || []);
  };
  ctx.font = font(500);
  const rows = model.lines.map((l) => {
    const control = l.row === 'home' ? u * 1.7 : l.row === 'compass' ? u * 2.9 : 0;
    const text = wrap(l.text, width - pad - valueX - control);
    return { l, control, text, h: Math.max(l.dial ? u * 2.7 : u * 1.65, text.length * u * 1.3 + u * 0.4) };
  });
  const height = u * 0.6 + u * 1.6 + rows.reduce((n, r) => n + r.h, 0) + u * 0.45;
  const x = o.x ?? W * 0.03;
  const y = o.y ?? (W >= H ? H * 0.05 : H * 0.575);
  ctx.fillStyle = 'rgba(255,255,255,0.88)';
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, u);
  ctx.fill();
  ctx.fillStyle = '#2c3a33';
  ctx.font = font(700, u * 1.08);
  ctx.fillText(model.title, x + pad, y + u * 0.6 + u * 0.8);
  let top = y + u * 0.6 + u * 1.6;
  for (const { l, control, text, h } of rows) {
    const mid = top + h / 2;
    ctx.font = font(500);
    ctx.fillStyle = '#5d6b63';
    ctx.fillText(l.name, x + pad, mid);
    const cx = x + valueX;
    if (l.share !== undefined) {
      const textW = text[0] ? ctx.measureText(text[0]).width + u * 0.5 : 0;
      const bw = width - pad - valueX - textW;
      ctx.fillStyle = 'rgba(44,58,51,0.12)';
      ctx.beginPath();
      ctx.roundRect(cx, mid - u * 0.28, bw, u * 0.55, u * 0.3);
      ctx.fill();
      ctx.fillStyle = l.low ? '#d9822b' : '#6aa84f';
      ctx.beginPath();
      ctx.roundRect(cx, mid - u * 0.28, Math.max(u * 0.55, bw * Math.max(0, Math.min(1, l.share))), u * 0.55, u * 0.3);
      ctx.fill();
    }
    if (l.row === 'home' && l.arrow !== undefined) arrow(ctx, cx + u * 0.55, mid, u * 0.55, l.arrow, '#3f7a38');
    if (l.dial) {
      const r = u * 1.2;
      const dx = cx + r;
      ctx.strokeStyle = 'rgba(44,58,51,0.35)';
      ctx.lineWidth = Math.max(2, u * 0.1);
      ctx.beginPath();
      ctx.arc(dx, mid, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.save();
      ctx.translate(dx, mid);
      ctx.rotate(l.dial.north);
      ctx.font = font(700, u * 0.62);
      ctx.fillStyle = '#b5532a';
      ctx.textAlign = 'center';
      ctx.fillText('N', 0, -r + u * 0.45);
      ctx.restore();
      ctx.textAlign = 'left';
      arrow(ctx, dx, mid, r * 0.5, l.dial.north + l.dial.needle, '#3f7a38', true);
    }
    ctx.fillStyle = '#2c3a33';
    ctx.font = font(500);
    const tx = l.share !== undefined ? x + width - pad - ctx.measureText(text[0] ?? '').width : cx + control;
    text.forEach((t, i) => ctx.fillText(t, tx, mid + (i - (text.length - 1) / 2) * u * 1.3));
    top += h;
  }
}

// an arrow of length len about (x, y), turned clockwise of up by angle; fromCentre: it starts at (x, y) instead of straddling it
function arrow(ctx, x, y, len, angle, color, fromCentre = false) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  const tail = fromCentre ? 0 : len;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = Math.max(3, len * 0.28);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(0, tail);
  ctx.lineTo(0, -len * 0.3);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(0, -len);
  ctx.lineTo(len * 0.5, -len * 0.3);
  ctx.lineTo(-len * 0.5, -len * 0.3);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function press(canvas, { key, zoom }) {
  if (zoom) canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: zoom, clientX: canvas.width / 2, clientY: canvas.height / 2, bubbles: true, cancelable: true }));
  else dispatchEvent(new KeyboardEvent('keydown', { key }));
}

// shots: [{from, to, speed}] and labels: [{from, to, lines}] in replay seconds; keys: [{at, key}] or [{at, zoom}]
// (a mouse wheel turn on the canvas, + out, - in: portrait needs the overview pulled back to fit the arena);
// hold: seconds to keep the last frame, showing end on the clock (the replay clock rounds down);
// tag: a small label in a grid cell; demo: the scripted demo rather than a replay;
// vitals: true draws the followed nim's senses card on the clip under any camera (or {scale, x, y} in px);
// top: the labels' first line y; clockAt: the clock's y, else under the labels; tags: [{text, from, to, x, y, size}]
export async function clip({ name, shots, labels = [], keys = [], hold = 0, end, clock = false, size = [1080, 1920], tag, tags = [], top = 360, clockAt, demo = false, vitals = false }) {
  const [W, H] = size;
  await loadFonts();
  const { gl, label, step } = await setup(size, demo);
  dispatchEvent(new KeyboardEvent('keydown', { key: 'r' }));
  if (vitals) window.terrariumVitals.force(true);
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
      while (pending.length && pending[0].at <= t) press(gl, pending.shift());
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
    if (vitals) vitalsCard(ctx, window.terrariumVitals.model(), W, H, vitals === true ? {} : vitals);
    const on = labels.find((l) => t >= (l.from ?? 0) && t < (l.to ?? Infinity));
    // the clock sits with the labels, so all the text is read in one place and the eyes stay on the footage
    const below = on ? lines(ctx, on.lines, W, top) + 16 : top;
    if (clock) pill(ctx, time, W, clockAt ?? below);
    const tg = tags.find((l) => t >= (l.from ?? 0) && t < (l.to ?? Infinity));
    if (tg) {
      ctx.textAlign = 'left';
      text(ctx, tg.text, tg.x ?? 24, tg.y ?? 64, [HEAD[0], 700, tg.size ?? 44], W - 48, BOX);
    }
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
