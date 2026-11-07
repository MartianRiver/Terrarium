import { advance, care, clock, hatch, HOUR, isAsleep, mood, nextAt, readCare, SAVE_KEY, stage, type Care, type CareAction } from './petcare';
import { petWorld } from './petworld';
import './pet.css';

const app = document.querySelector<HTMLElement>('#app')!;
const debug = new URLSearchParams(location.search).has('debug');
app.innerHTML = `
  <header><a class="wordmark" href="/pet.html">Terrarium<span>A little life, in your care</span></a>
    <div class="edition">THE PET NURSERY <span>Local prototype · 01</span></div></header>
  <div class="layout">
    <section class="garden" aria-label="Your nim's interactive terrarium">
      <div id="world"></div>
      <div class="garden-title"><span class="eyebrow">YOUR LITTLE CORNER OF MARS</span><h1>Your nim’s nursery</h1></div>
      <button id="home" class="view-button" aria-label="Reset garden camera">Garden view ↗</button>
      <div class="garden-caption"><span class="live-dot"></span><span id="activity">A garden waiting for a little life.</span></div>
      <p class="gesture">Drag to look around · scroll to zoom · tap your nim to say hello</p>
      <div id="welcome" class="welcome"><span class="eyebrow">MEET YOUR NIM</span><h2>A small world.<br>A little responsibility.</h2>
        <p>Feed it. Play together. Clean up the inevitable.<br>This little one depends on you.</p><button id="adopt" class="primary">Bring your nim home <span>↗</span></button>
        <small>Needs keep changing while you’re away.</small></div>
      <div id="farewell" class="welcome" hidden><span class="eyebrow">YOUR NIM HAS GONE</span><h2>Your nim has gone to rest.</h2>
        <p>Thank you for looking after it. Little ones need a meal, a tidy garden, company and medicine when they’re ill; a new egg can try again.</p><button id="again" class="primary">Hatch a new egg <span>↗</span></button></div>
    </section>
    <aside aria-label="Care for your nim">
      <div class="identity"><div class="avatar" aria-hidden="true">n.</div><div><span class="eyebrow">YOUR NIM</span><h2 id="mood">A new beginning</h2><p id="age">Ready when you are.</p></div></div>
      <div id="needs" aria-label="Your nim's needs">
        ${[['fullness', 'Tummy', 'A meal when hungry'], ['happiness', 'Happiness', 'Play & a little attention'], ['health', 'Wellbeing', 'Regular care keeps it well']].map(([id, label, help]) => `
          <div class="need"><div><label for="${id}">${label}</label><output id="${id}-value">—</output></div>
          <meter id="${id}" min="0" max="100" low="25" optimum="100" value="0">0</meter><small>${help}</small></div>`).join('')}
      </div>
      <div class="care-actions"><button data-care="feed"><span class="action-icon">◒</span><span>Feed your nim<small>A little meal</small></span><span>↗</span></button>
        <button data-care="play"><span class="action-icon">◉</span><span>Play together<small>Chase the golden ball</small></span><span>↗</span></button>
        <button data-care="clean"><span class="action-icon">✳</span><span>Clean up<small id="mess-count">A fresh little garden</small></span><span>↗</span></button>
        <button data-care="stroke"><span class="action-icon">♡</span><span>Say hello<small>A little affection</small></span><span>↗</span></button>
        <button data-care="medicine" class="wide"><span class="action-icon">✚</span><span>Medicine<small>Only when your nim is ill</small></span><span>↗</span></button></div>
      <p id="message" role="status" aria-live="polite">Opening your saved nursery…</p>
      <button id="retry" hidden>Retry opening saved nursery</button>
      <div class="journal"><span class="eyebrow">LITTLE MOMENTS</span><ol id="journal"></ol></div>
      <details><summary>About this little prototype</summary><p>Your nursery saves in this browser on this Mac. Needs catch up when you return, even if the tab or computer was closed.</p>
        <p>Prototype rhythm: a full tummy lasts about 8 hours; a meal becomes a poop after 30 minutes. Mess and hunger make happiness fall faster. Neglect lowers wellbeing. Your nim sleeps from 20:00 to 07:30 and its needs barely move then. Left unfed, unplayed with or in a mess for 8 hours it falls ill, and without medicine it dies 12 hours later.</p>
        <p>Your nim’s movements are scripted for this demo. Your care changes its needs; it doesn’t train a brain.</p>
        <button id="export">Download nursery save</button></details>
      ${debug ? `<div class="debug"><span class="eyebrow">DEBUG TIME</span><div>
        <button data-skip="${HOUR / 2}">+30 min</button><button data-skip="${HOUR}">+1 h</button><button data-skip="${8 * HOUR}">+8 h</button>
        <button data-clock="1200">→ 20:00</button><button data-clock="450">→ 07:30</button></div><p id="demo-time"></p></div>` : ''}
    </aside>
  </div>
  <footer>Small rituals. A life of its own.<span>TERRARIUM / NURSERY STUDIES</span></footer>`;

const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
let current: Care | null = null;
let failed = false;
let world: ReturnType<typeof petWorld> | null = null;
let lastSave = 0;
let rawSave: string | null = null;
let greeting = '';

function message(text: string, error = false) {
  el('message').textContent = text;
  el('message').classList.toggle('error', error);
}

function now() { return Date.now() + (current?.offset ?? 0); }

function persist() {
  if (!current) return;
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify(current));
    lastSave = Date.now();
  } catch {
    failed = true;
    message('Your browser could not save your nim. Download the save below before closing, then retry.', true);
    el('retry').hidden = false;
  }
}

function open() {
  try {
    rawSave = localStorage.getItem(SAVE_KEY);
    current = rawSave ? readCare(rawSave) : null;
    const away = current ? Math.max(0, Date.now() + current.offset - current.updated) : 0;
    if (current) advance(current, now());
    failed = false;
    el('retry').hidden = true;
    greeting = away >= 60_000 ? `Welcome back. ${Math.floor(away / 60_000)} minutes passed; your nim’s needs have caught up.` : 'Your nursery is saved here. A little care goes a long way.';
    message(current?.dead ? 'Your nim has gone.' : current ? greeting : 'Your first little nim is waiting to come home.');
    if (current) persist();
  } catch (error) {
    failed = true;
    message(error instanceof Error ? error.message : 'Could not open the nursery save. It has been kept.', true);
    el('retry').hidden = false;
  }
  refresh();
}

function refresh() {
  el('welcome').hidden = !!current || failed;
  el('farewell').hidden = !current?.dead;
  el<HTMLButtonElement>('adopt').disabled = failed;
  for (const btn of document.querySelectorAll<HTMLButtonElement>('[data-care], [data-skip], [data-clock]')) btn.disabled = !current || failed || current.dead;
  el<HTMLButtonElement>('export').disabled = !current && !rawSave;
  if (!current) return;
  el('mood').textContent = mood(current);
  const hours = Math.floor(((current.dead ? current.died : current.updated) - current.born) / HOUR);
  el('age').textContent = hours < 1 ? 'Settling into its new home' : `${hours} hour${hours === 1 ? '' : 's'} in your care`;
  for (const key of ['fullness', 'happiness', 'health'] as const) {
    el<HTMLMeterElement>(key).value = current[key];
    el(`${key}-value`).textContent = `${Math.round(current[key])}%`;
  }
  el('mess-count').textContent = current.mess.length ? `${current.mess.length} little poop${current.mess.length === 1 ? '' : 's'} to clear` : 'All clean';
  el('activity').textContent = current.dead ? 'Your nim has gone.' : stage(current) === 'very ill' ? 'Your nim is very ill. Medicine, quickly.'
    : stage(current) === 'ill' ? 'Your nim is ill and needs medicine.' : stage(current) === 'poorly' ? 'Your nim is not feeling well. Some care would help.'
    : isAsleep(current, current.updated) ? `Your nim is asleep until ${clock(current.wake)}.` : current.mess.length ? 'A little cleanup would be lovely.' : current.fullness < 25 ? 'Someone’s ready for a meal.' : current.happiness < 30 ? 'A little company would be lovely.' : 'Pottering around, making this place its own.';
  if (debug) el('demo-time').textContent = `${new Date(current.updated).toLocaleString()} · neglect ${(current.neglect / HOUR).toFixed(1)} h · ill ${(current.sickFor / HOUR).toFixed(1)} h · demo +${(current.offset / HOUR).toFixed(1)} h`;
  const list = el('journal');
  list.replaceChildren(...current.history.slice(0, 4).map(item => {
    const li = document.createElement('li');
    const time = document.createElement('span');
    const minutes = Math.max(0, Math.floor((current!.updated - item.at) / 60_000));
    time.textContent = minutes < 1 ? 'Just now' : minutes < 60 ? `${minutes}m ago` : `${Math.floor(minutes / 60)}h ago`;
    const text = document.createElement('p'); text.textContent = item.text;
    li.append(time, text); return li;
  }));
}

function act(action: CareAction) {
  if (!current || failed) return;
  advance(current, now());
  const result = care(current, action);
  if (result.ok) { world?.react(action); persist(); }
  if (!failed) message(result.text);
  refresh();
}

el('adopt').addEventListener('click', () => {
  if (failed) return;
  current = hatch(Date.now());
  persist(); refresh();
  if (!failed) message('Welcome home. Try a meal or a little game together.');
});
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-care]')) {
  button.addEventListener('click', () => act(button.dataset.care as CareAction));
}
function jump(ms: number, text: string) {
  if (!current || failed || current.dead) return;
  current.offset += ms;
  advance(current, now()); persist(); refresh();
  if (!failed) message(current.dead ? 'Your nim has gone.' : text);
}
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-skip]')) {
  button.addEventListener('click', () => jump(Number(button.dataset.skip), `${button.textContent} passed. Care catches up through the same rules as real time.`));
}
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-clock]')) {
  button.addEventListener('click', () => jump(nextAt(now(), Number(button.dataset.clock)) - now(), `Jumped ${button.textContent}.`));
}
el('again').addEventListener('click', () => {
  if (failed) return;
  current = hatch(Date.now());
  persist(); refresh();
  if (!failed) message('A new egg hatched. Welcome home.');
});
el('export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([current ? JSON.stringify(current, null, 2) : rawSave ?? ''], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = 'nim-nursery.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
el('retry').addEventListener('click', () => {
  // A write failure may leave newer in-memory care than the disk copy.
  if (current && failed) { failed = false; persist(); if (!failed) { el('retry').hidden = true; message('Your nursery is saved again.'); } refresh(); }
  else open();
});
el('home').addEventListener('click', () => world?.home());
open();
try { world = petWorld(el('world'), () => current, () => act('stroke')); }
catch { message('The 3D garden could not open. Try a browser with WebGL enabled; the care controls and save still work.', true); }
setInterval(() => {
  if (!current || failed) return;
  const alive = !current.dead;
  advance(current, now());
  if (Date.now() - lastSave > 10_000 || (alive && current.dead)) persist();
  refresh();
}, 1000);
document.addEventListener('visibilitychange', () => {
  if (!current || failed) return;
  advance(current, now()); persist(); refresh();
});
window.addEventListener('pagehide', () => { if (current && !failed) { advance(current, now()); persist(); } });
window.addEventListener('storage', e => {
  if (e.key === SAVE_KEY) {
    failed = true;
    message('This nursery changed in another tab. Reload this page before caring for your nim.', true);
    refresh();
  }
});
