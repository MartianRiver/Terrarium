// Catch them!, the kids page (kids.html, served by sim kidsserve.py): pick a game by its picture, a 3-2-1, ninety
// seconds of being it, then how many you caught, the stars that earned, and one big button to go again. Nothing needs
// reading. The camera holds still over the room unless a gamepad's right stick (or Q and E) turns it, so pointing at
// a Terrikin is walking to it. A gamepad does everything: the left stick walks (and on the picture screen moves along
// the game, who you are and your colour), A starts, A, a bumper or the right trigger sprints (turbo in the little
// room, where snacks fill it), X honks, Y puts the camera back, Menu pauses. A game goes fullscreen (&window keeps it
// in the window). Progress (stars, levels, who you are) stays in this browser.
import { dress as wear } from './costumes';
import { Beeps, CatchFx } from './kidsfx';
import { KidsGame, type Device } from './kidsgame';
import { Menu, type Choice, type Levels, type Row } from './kidsmenu';
import { Pad } from './kidspad';
import { COLOURS, LOOKS, load, record, save, type Look } from './kidsprogress';
import { Snacks } from './kidssnacks';
import { createLogger } from './lib/logger';
import { createStage } from './stage';
import type { Frame, WorldInfo } from './world';
import { WorldView } from './worldview';

const log = createLogger('kids');

// how near the camera comes: the little room whole, the big ones closer, following you
const NEARER: Record<string, number> = { little: 1, big: 0.62 };
// the end screen's buttons wait this long, so a click meant for the game doesn't start the next one
const SETTLE = 1500;
const EMPTY: WorldInfo = { width: 12, height: 12, tickHz: 20, maxSpeed: 2, nests: [], midden: 0 };
const TURN = 1.6; // radians a second at full stick
const ZOOM = 0.8; // share a second
const CLOSEST = 0.45;

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function boot() {
  const params = new URLSearchParams(location.search);
  const stage = createStage($('#world'), params.has('lite'));
  stage.holdStill();
  stage.setWorld(EMPTY);
  const fx = new CatchFx(stage.scene);
  const snacks = new Snacks(stage.scene);
  const turbo = $('#turbo');
  const fuel = $('#turbo div span');
  const role = $('#role');
  const beeps = new Beeps();
  const pad = new Pad();
  const canvas = stage.renderer.domElement;
  const hud = $('#kids-hud');
  const count = $('#count');
  const bar = $('#time span');
  const big = $('#big');
  const status = $('#status');
  const soundButton = $<HTMLButtonElement>('#sound');

  let game: KidsGame | null = null;
  let view: WorldView | null = null;
  let choice: Choice = { mode: 'little', level: 1 };
  let row: Row = 'game';
  let fueled = 0;
  let boosting = false;
  let phase: 'pick' | 'starting' | 'counting' | 'playing' | 'paused' | 'end' = 'pick';
  let device: Device = 'mouse';
  let progress = load();
  let acc = 0;
  let last = performance.now();
  let settled = 0;
  let lastTick = -1;
  let warned = 0;
  let lit = 0;
  let yaw = 0;
  let zoom = 1;

  function show(kind: 'error' | 'loading' | 'ok', text = '') {
    status.dataset.kind = kind;
    status.textContent = text;
    status.hidden = kind === 'ok';
  }

  show('loading', 'Getting the room ready…');
  let levels: Levels;
  try {
    const res = await fetch('/api/kids');
    if (!res.ok) throw new Error(`the server said ${res.status}`);
    const got: { modes: Record<string, { stars: [number, number] }[]> } = await res.json();
    levels = Object.fromEntries(Object.entries(got.modes).map(([m, ls]) => [m, ls.map((l) => l.stars)]));
    show('ok');
  } catch (err) {
    log.error('modes failed to load', { err });
    show('error', 'The game’s server isn’t answering. Is terrarium.kidsserve running?');
    return;
  }
  const menu = new Menu(levels, (c) => void begin(c), dress, paint);

  function screen(next: typeof phase) {
    phase = next;
    $('#pick').hidden = next !== 'pick';
    $('#end').hidden = next !== 'end';
    hud.hidden = !['counting', 'playing', 'paused'].includes(next);
    turbo.hidden = hud.hidden || !game?.canSprint || choice.mode !== 'little';
    document.body.dataset.phase = next;
  }

  function showPick() {
    screen('pick');
    menu.showPick(progress, choice, row);
  }

  function dress(look: Look) {
    progress = { ...progress, look };
    save(progress);
    beeps.wake();
    beeps.honk(look);
    row = 'look';
    menu.showPick(progress, choice, row);
  }

  function paint(colour: number) {
    progress = { ...progress, colour };
    save(progress);
    beeps.wake();
    beeps.count();
    row = 'colour';
    menu.showPick(progress, choice, row);
  }

  async function begin(next: Choice) {
    if (phase === 'starting') return;
    beeps.wake();
    // fullscreen, so there are no tabs or bars to wander off to (&window keeps it in the window)
    if (!document.fullscreenElement && !params.has('window')) document.documentElement.requestFullscreen?.().catch(() => {});
    choice = next;
    screen('starting');
    show('loading', 'Waking them up…');
    try {
      const started = await KidsGame.begin(next.mode, next.level, stage.camera, canvas, device, pad, progress.colour);
      game?.end('again');
      game = started;
      view?.dispose();
      fx.clear();
      snacks.clear();
      stage.setWorld(started.info);
      view = new WorldView(stage.scene, started.info, false);
      view.chosen = started.you;
      view.marked = true;
      const look = progress.look;
      if (look !== 'terrikin') view.dress = (id, blob) => id === started.you && wear(blob, look);
      const first = started.step()!;
      view.push(first);
      lastTick = first.tick;
      acc = warned = lit = fueled = 0;
      role.hidden = true;
      fuel.style.width = '0%';
      count.textContent = '0';
      menu.goals(0, menu.targets(next));
      bar.style.width = '100%';
      $('#level').textContent = next.mode === 'big' ? String(next.level) : '';
      show('ok');
      log.info('game started', { ...next, device });
      void countdown();
    } catch (err) {
      log.error('game failed to start', { err });
      show('error', `The game didn’t start: ${err instanceof Error ? err.message : String(err)}`);
      showPick();
    }
  }

  async function countdown() {
    screen('counting');
    for (const word of ['3', '2', '1']) {
      say(word);
      beeps.count();
      await wait(700);
      if (phase !== 'counting') return;
    }
    say('Go!');
    beeps.count(true);
    screen('playing');
    game!.going = true;
    setTimeout(() => phase === 'playing' && say(''), 600);
  }

  function say(word: string) {
    big.textContent = word;
    big.classList.remove('pop');
    void big.offsetWidth;
    if (word) big.classList.add('pop');
  }

  function pause(on: boolean) {
    if (!game || (on ? phase !== 'playing' : phase !== 'paused')) return;
    game.going = !on;
    screen(on ? 'paused' : 'playing');
    say(on ? '⏸' : '');
    acc = 0;
  }

  function finish() {
    const g = game!;
    const caught = g.score.catches;
    const count = levels[choice.mode].length;
    const [next, round] = record(progress, choice.mode, choice.level, count, caught, menu.targets(choice));
    progress = next;
    save(progress);
    menu.showEnd(caught, round, choice.level < count && choice.level < menu.latest(choice.mode).level);
    beeps.fanfare(round.record || round.opened !== null);
    settled = performance.now() + SETTLE;
    $('#end').classList.add('settling');
    setTimeout(() => $('#end').classList.remove('settling'), SETTLE);
    say('');
    screen('end');
    log.info('game over', { ...choice, caught, stars: round.stars, opened: round.opened, device: g.device });
  }

  function home() {
    game?.end('home');
    game = null;
    snacks.clear();
    say('');
    showPick();
  }

  function again() {
    if (performance.now() > settled) void begin(choice);
  }

  function onward() {
    if (performance.now() > settled && !$('#next').hidden) void begin({ ...choice, level: choice.level + 1 });
  }

  // a catch: stars where it happened, a boing, a buzz, and the count jumps
  function celebrate(at: { x: number; y: number }) {
    fx.burst(at.x, at.y);
    beeps.boing();
    pad.buzz(0.5, 0.9, 160);
    const n = game!.score.catches;
    count.textContent = String(n);
    count.classList.remove('bump');
    void count.offsetWidth;
    count.classList.add('bump');
    const now = menu.goals(n, menu.targets(choice));
    if (now > lit && now > 1) beeps.fanfare(false);
    lit = now;
  }

  // tag back: they caught you, so you're it, and the run badge goes
  function uhOh(at: { x: number; y: number }) {
    fx.burst(at.x, at.y, 0.45, false);
    beeps.uhOh();
    pad.buzz(0.9, 0.4, 220);
  }

  // sent home: a puff where it was, and one in the nest
  function puff(h: { x: number; y: number; tx?: number; ty?: number }) {
    fx.burst(h.x, h.y, 0.35, false);
    if (h.tx !== undefined && h.ty !== undefined) fx.burst(h.tx, h.ty, 0.35, false);
  }

  function honk() {
    if (!view?.focus) return;
    beeps.honk(progress.look);
    fx.honk(view.focus.x, view.focus.y);
  }

  // left and right along a row of the picture screen: the games, who you are, your colour
  function step(by: number) {
    document.body.classList.add('steering');
    const around = <T,>(all: readonly T[], now: T) => all[(all.indexOf(now) + by + all.length) % all.length];
    if (row === 'look') return dress(around(LOOKS, progress.look));
    if (row === 'colour') return paint(around(COLOURS, progress.colour as (typeof COLOURS)[number]));
    const all = menu.choices(progress);
    const i = all.findIndex((c) => c.mode === choice.mode && c.level === choice.level);
    choice = all[(i + by + all.length) % all.length];
    menu.showPick(progress, choice, row);
  }

  // up and down between the rows
  function climb(by: number) {
    document.body.classList.add('steering');
    const rows = menu.rows(progress);
    row = rows[Math.max(0, Math.min(rows.length - 1, rows.indexOf(row) + by))];
    menu.showPick(progress, choice, row);
  }

  // snacks eaten since the last frame, and the turbo bar
  function fill() {
    for (const s of snacks.set(game!.score.snacks)) {
      fx.burst(s.x, s.y, 0.4, false);
      beeps.nom();
      turbo.classList.remove('gulp');
      void turbo.offsetWidth;
      turbo.classList.add('gulp');
    }
    const now = game!.score.turbo;
    const going = now < fueled - 1e-4;
    if (going && !turbo.classList.contains('going')) beeps.whoosh();
    turbo.classList.toggle('going', going);
    boosting = going;
    turbo.classList.toggle('full', now >= 0.99);
    fuel.style.width = `${now * 100}%`;
    fueled = now;
  }

  $('#again').addEventListener('click', again);
  $('#next').addEventListener('click', onward);
  $('#home').addEventListener('click', () => performance.now() > settled && home());
  $('#quit').addEventListener('click', home);
  soundButton.addEventListener('click', () => {
    beeps.wake();
    beeps.toggle();
    soundButton.setAttribute('aria-pressed', String(beeps.on));
  });
  soundButton.setAttribute('aria-pressed', String(beeps.on));
  addEventListener('pointermove', (e) => {
    if (e.movementX || e.movementY) document.body.classList.remove('steering');
  });
  addEventListener('pointerdown', (e) => {
    device = e.pointerType === 'mouse' ? 'mouse' : 'touch';
    // paused, any click or tap goes on
    if (phase === 'paused' && e.target !== $('#quit')) pause(false);
  }, true);
  const turning = new Set<string>();
  addEventListener('keyup', (e) => turning.delete(e.key.toLowerCase()));
  addEventListener('keydown', (e) => {
    device = 'keys';
    const key = e.key.toLowerCase();
    if (key === 'q' || key === 'e') turning.add(key);
    if (key === 'h') honk();
    if (key === 'escape' && ['playing', 'counting', 'paused'].includes(phase)) home();
    if (key === 'p') pause(phase === 'playing');
    else if (phase === 'paused' && key !== 'escape') pause(false);
    if (phase === 'pick') {
      if (key === 'arrowleft' || key === 'arrowright') step(key === 'arrowleft' ? -1 : 1);
      if (key === 'arrowup' || key === 'arrowdown') climb(key === 'arrowup' ? -1 : 1);
      if (key === 'enter' || key === ' ') void begin(choice);
    } else if (phase === 'end' && (key === 'enter' || key === ' ')) again();
  });
  addEventListener('pagehide', () => game?.end('quit'));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && phase === 'playing') pause(true);
  });

  let side = 0;
  let upDown = 0;
  function gamepad(dt: number) {
    pad.poll();
    if (!pad.connected) return;
    if (pad.any()) device = 'pad';
    const s = Math.abs(pad.move.x) > 0.5 ? Math.sign(pad.move.x) : 0;
    const v = Math.abs(pad.move.y) > 0.5 ? Math.sign(pad.move.y) : 0;
    if (phase === 'pick') {
      if (s && s !== side) step(s);
      if (v && v !== upDown) climb(v);
      if (pad.pressed('a') || pad.pressed('menu')) void begin(choice);
      if (pad.pressed('x') || pad.pressed('b')) dress(LOOKS[(LOOKS.indexOf(progress.look) + 1) % LOOKS.length]);
    } else if (phase === 'end') {
      if (pad.pressed('a')) again();
      if (pad.pressed('rb') || pad.pressed('right')) onward();
      if (pad.pressed('view')) home();
    } else {
      if (pad.pressed('menu') || (phase === 'paused' && pad.pressed('a'))) pause(phase === 'playing');
      if (pad.pressed('view') && phase === 'paused') home();
      if (pad.pressed('x') || pad.pressed('b')) honk();
      if (pad.pressed('y')) {
        yaw = 0;
        zoom = 1;
      }
      yaw -= pad.look.x * TURN * dt;
      zoom += pad.look.y * ZOOM * dt;
    }
    side = s;
    upDown = v;
  }

  const gap = params.has('lite') ? 1000 / 30 - 2 : 0;
  function frame(now: number) {
    requestAnimationFrame(frame);
    if (now - last < gap) return;
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    gamepad(dt);
    yaw += ((turning.has('q') ? 1 : 0) - (turning.has('e') ? 1 : 0)) * TURN * dt;
    zoom = Math.max(CLOSEST, Math.min(1, zoom));
    if (game && view && phase === 'playing') {
      const tickSeconds = 1 / game.info.tickHz;
      acc += dt;
      while (acc >= tickSeconds) {
        if (!game.ready()) {
          acc = Math.min(acc, tickSeconds);
          break;
        }
        const next: Frame | null = game.step();
        if (!next) {
          finish();
          break;
        }
        if (next.tick !== lastTick) {
          view.push(next);
          lastTick = next.tick;
          for (const h of game.happenedBy(next.tick)) {
            if (h.kind === 'catch') celebrate(h);
            else if (h.kind === 'tagged') uhOh(h);
            else puff(h);
          }
          fill();
        }
        acc -= tickSeconds;
      }
      // tag back: run while someone else is it
      const running = !game.score.it;
      if (running !== !role.hidden) {
        role.hidden = !running;
        if (running) {
          say('🏃');
          setTimeout(() => big.textContent === '🏃' && say(''), 800);
        }
      }
      const left = Math.max(0, game.score.length - game.score.seconds);
      bar.style.width = `${(100 * left) / game.score.length}%`;
      hud.classList.toggle('hurry', left <= 10);
      // the last five seconds tick
      if (left <= 5 && left > 0 && Math.ceil(left) !== warned) {
        warned = Math.ceil(left);
        beeps.tick();
      }
      if (game.failed) {
        show('error', `The game stopped: ${game.failed}`);
        home();
      }
    }
    const moving = phase === 'playing';
    if (view) view.render(moving ? acc * (game?.info.tickHz ?? 20) : 1, moving ? dt : 0, now / 1000);
    fx.render(dt, now / 1000, view?.current ?? null, moving || phase === 'paused' ? game?.score.dizzy ?? [] : []);
    const on = boosting && moving && !!game;
    document.body.classList.toggle('turbo', on);
    fx.turbo(dt, now / 1000, on ? view?.focus ?? null : null);
    snacks.render(dt, now / 1000);
    const near = (NEARER[choice.mode] ?? 1) * zoom;
    const me = phase === 'pick' ? null : view?.focus;
    stage.over(me ?? { x: 0, y: 0 }, near, dt, yaw);
    stage.render(now / 1000);
  }

  showPick();
  requestAnimationFrame(frame);
}

window.addEventListener('error', (e) => log.error('uncaught error', e.error ?? e.message));
window.addEventListener('unhandledrejection', (e) => log.error('unhandled rejection', e.reason));

boot().catch((err) => {
  log.error('boot failed', err);
  const status = document.getElementById('status')!;
  status.dataset.kind = 'error';
  status.textContent = `Something broke while starting up: ${err instanceof Error ? err.message : String(err)}`;
  status.hidden = false;
});
