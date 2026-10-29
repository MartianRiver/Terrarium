// Builds the public site's pages from ../site into OUT, next to the viewer at OUT/watch/.
// node site.mjs OUT [--review [--marked]]   (SITE_CLIPS=DIR: the clips backups folder, when a post shows a clip)
// --review adds the drafts (SITE_DRAFTS, or site/drafts/; never committed) and keeps search engines out. They look
// exactly as they will when published, unless --marked adds a review bar, DRAFT tags and where each clip came from.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { marked } from 'marked';

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = join(HERE, '..', 'site');
const CACHE = join(HERE, 'node_modules', '.cache', 'site-clips');
const ORIGIN = 'https://terrarium.martianriver.com';
const REPO = 'https://github.com/MartianRiver/Terrarium';
const INSTAGRAM = 'https://www.instagram.com/martianriver/';

const args = process.argv.slice(2);
const out = args[0];
if (!out) throw new Error('usage: node site.mjs OUT [--review [--marked]]');
const review = args.includes('--review');
const marks = review && args.includes('--marked');
const media = process.env.SITE_CLIPS;
// a half-built public site must never be deployed: rsync --delete would leave the server with only the viewer
process.on('uncaughtException', (e) => {
  if (!review) rmSync(out, { recursive: true, force: true });
  console.error(`site: ${e.message}`);
  process.exit(1);
});
const clips = JSON.parse(readFileSync(join(SITE, 'clips.json'), 'utf8'));

function read(path) {
  const text = readFileSync(path, 'utf8');
  const m = text.match(/^---\n([\s\S]*?)\n---\n/);
  const meta = {};
  for (const line of (m?.[1] ?? '').split('\n')) {
    const i = line.indexOf(':');
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return { meta, body: m ? text.slice(m[0].length) : text };
}

const escape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// a plain day or a full ISO time with its offset (2026-10-24T17:00+11:00); pages show the day in Sydney
const when = (iso) => new Date(iso.includes('T') ? iso : `${iso}T12:00:00+11:00`);

function date(iso) {
  return when(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Australia/Sydney' });
}

function page({ title, description, path, body, wide = false }) {
  const full = title === 'Terrarium' ? title : `${title} · Terrarium`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${marks ? 'REVIEW · ' : ''}${escape(full)}</title>
<meta name="description" content="${escape(description)}">${review ? '\n<meta name="robots" content="noindex, nofollow">' : ''}
<meta property="og:title" content="${escape(full)}">
<meta property="og:description" content="${escape(description)}">
<meta property="og:image" content="${ORIGIN}/card.jpg">
<meta property="og:url" content="${ORIGIN}${path}">
<meta name="twitter:card" content="summary_large_image">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cellipse cx='8' cy='9.5' rx='6' ry='5.5' fill='%23f08a6c'/%3E%3Ccircle cx='8' cy='3' r='1.6' fill='%23c46d40'/%3E%3C/svg%3E">
<link rel="stylesheet" href="/site.css">
</head>
<body>
${marks ? '<p class="review">Review build: drafts are shown and marked. Not the public site.</p>\n' : ''}<header class="top">
  <a class="name" href="/">Terrarium</a>
  <nav aria-label="Site">
    <a href="/watch/">Watch</a>
    <a href="/brains/">Brains</a>
    <a href="/blog/">Blog</a>
    <a href="/at-home/">At Home</a>
    <a href="${REPO}">Code</a>
  </nav>
</header>
<main${wide ? ' class="wide"' : ''}>
${body}
</main>
<footer>
  <p>Made by River James (Martian River). <a href="${INSTAGRAM}">Instagram</a> · <a href="${REPO}">GitHub</a> · <a href="/how/">How this is made</a> · MIT licence. No cookies, no tracking.</p>
</footer>
</body>
</html>
`;
}

function write(path, html) {
  const file = join(out, path, 'index.html');
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, html);
}

// crop is ffmpeg's w:h:x:y; without one a clip is 16:9
function height(clip) {
  const [w, h] = clip.crop ? clip.crop.split(':').map(Number) : [16, 9];
  return Math.round((clip.width * h) / w);
}

// {{clip name}} is a short muted loop from clips.json; {{youtube ID Title}} loads YouTube only when clicked
function embeds(body, post, used) {
  return body
    .replace(/\{\{clip ([\w-]+)\}\}/g, (_, name) => {
      const clip = clips[name];
      if (!clip) throw new Error(`${post.file}: no clip "${name}" in clips.json`);
      used.add(name);
      const from = marks ? `\n<figcaption class="source">Clip from ${escape(clip.from)}, ${clip.start}–${clip.start + clip.seconds} s</figcaption>` : '';
      return `<figure class="clip"><video src="/media/${name}.mp4" poster="/media/${name}.jpg" width="${clip.width}" height="${height(clip)}" autoplay muted loop playsinline aria-label="${escape(clip.alt)}"></video>${from}</figure>`;
    })
    .replace(/\{\{youtube ([\w-]+) (.+?)\}\}/g, (_, id, title) => `<figure class="youtube"><button type="button" data-id="${id}">▶ ${escape(title)}<span>Plays on YouTube. Nothing loads from YouTube until you press it.</span></button></figure>`);
}

const YOUTUBE = `<script>
for (const b of document.querySelectorAll('.youtube button')) b.addEventListener('click', () => {
  const f = document.createElement('iframe');
  f.src = 'https://www.youtube-nocookie.com/embed/' + b.dataset.id + '?autoplay=1';
  f.title = b.firstChild.textContent;
  f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
  b.replaceWith(f);
});
</script>`;

function posts(dir, draft) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).filter((f) => f.endsWith('.md')).map((f) => {
    const { meta, body } = read(join(dir, f));
    // every post says which model drafted it and who edited it (/how/)
    // date is when it happened or went up on Instagram; written is when the post was, shown when they differ
    for (const key of ['title', 'date', 'written', 'summary', 'drafted', 'edited']) {
      if (!meta[key]) throw new Error(`${f} has no ${key}`);
    }
    for (const key of ['date', 'written']) {
      if (Number.isNaN(when(meta[key]).getTime())) throw new Error(`${f}: ${key} isn't a date: ${meta[key]}`);
    }
    return { ...meta, file: f, slug: f.replace(/^\d{4}-\d{2}-\d{2}-/, '').replace(/\.md$/, ''), body, draft };
  });
}

const notes = [...posts(join(SITE, 'blog'), false), ...(review ? posts(process.env.SITE_DRAFTS ?? join(SITE, 'drafts'), true) : [])]
  .sort((a, b) => when(b.date) - when(a.date));
const tag = (n) => (n.draft && marks ? ' <span class="draft">DRAFT</span>' : '');

const list = (items) =>
  `<ul class="notes">\n${items
    .map((n) => `<li><a href="/blog/${n.slug}/">${escape(n.title)}</a>${tag(n)}
  <span class="when">${date(n.date)}</span><p>${escape(n.summary)}</p></li>`)
    .join('\n')}\n</ul>`;

const home = read(join(SITE, 'index.md'));
const how = read(join(SITE, 'how.md'));
// nothing unfinished goes public: the same list as check.py's UNFINISHED. A review build still shows it
const UNFINISHED = [/^\W*DRAFT\b/m, /\bTBD\b/, /\bRiver (needs|has|is|still) to\b/i, /\bRiver to (write|add|check|fill|decide|review|edit|confirm)\b/i,
  /\b(River|me) to fill in\b/i, /\blorem\s+ipsum\b/i, /\[(fill|insert|add) [^\]]*\]/i, /\bplaceholder (text|paragraph|for River)\b/i];
const unfinished = [['index.md', home.body], ['how.md', how.body], ['at-home.md', read(join(SITE, 'at-home.md')).body],
  ...notes.filter((n) => !n.draft).map((n) => [n.file, n.body])];
for (const [name, text] of unfinished) {
  const hit = UNFINISHED.map((p) => text.match(p)?.[0]).find(Boolean);
  if (!review && hit) throw new Error(`site/${name} has something unfinished ("${hit}"), so it can't be published`);
}
const hero = `<section class="hero">
  <img src="/hero.jpg" width="1600" height="900" alt="A garden under a glass dome on a red plain. On the lawn inside, little round Terrikins in three colours gather berries around their nests.">
  <div class="pitch">
    <h1>Terrarium</h1>
    <p>${escape(home.meta.tagline)}</p>
    <a class="watch" href="/watch/">Watch them</a>
  </div>
</section>
<script>if (location.search) location.replace('/watch/' + location.search)</script>`;
const latest = notes.length ? `${list(notes.slice(0, 3))}\n<p><a href="/blog/">All the posts</a></p>` : '<p>Nothing written up yet.</p>';
write('', page({
  title: 'Terrarium',
  description: home.meta.description,
  path: '/',
  wide: true,
  body: `${hero}\n<div class="text">\n${marked(home.body).replace('<!-- posts -->', latest)}</div>`,
}));

write('how', page({
  title: how.meta.title,
  description: how.meta.description,
  path: '/how/',
  body: `<article>\n<h1>${escape(how.meta.title)}</h1>\n${marked(how.body)}</article>`,
}));

write('blog', page({
  title: 'Blog',
  description: 'Write-ups of what I tried, what worked and what didn’t.',
  path: '/blog/',
  body: `<h1>Blog</h1>\n<p>What I tried, what worked, what didn’t and what I tried next. The full lab record, every run and dead end, is in the repo’s <a href="${REPO}/tree/HEAD/docs/notes">docs/notes</a>.</p>\n${list(notes)}`,
}));

// the gallery itself (/replays/gallery/index.json and its replays) is published apart from the site, every 15 min
// while training runs (python -m terrarium.gallery), so the page reads it when it opens
const BRAINS = `<script>
const box = document.getElementById('gallery');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const ago = (iso) => { const m = Math.round((Date.now() - new Date(iso)) / 60000); return m < 90 ? m + ' min ago' : Math.round(m / 60) + ' h ago'; };
function brain(b, i, extra = '') {
  const n = b.numbers, bits = [];
  if (n.alive !== undefined) bits.push(n.alive + ' s alive');
  if (n.food_per_minute !== undefined) bits.push(n.food_per_minute + ' food a minute');
  if (n.stored !== undefined) bits.push(n.stored + ' stored');
  if (n.through_first_night) bits.push(n.through_first_night[0] + ' of ' + n.through_first_night[1] + ' colonies through night 1');
  if (n.from_middle !== undefined) bits.push(n.from_middle + ' food from the room, ' + n.blocks_moved + ' doors moved, per episode');
  const tested = n.episodes ? ' <span class="when">tested over ' + n.episodes + ' episodes</span>' : '';
  return '<li><a class="play" href="/watch/?replay=/replays/gallery/' + encodeURIComponent(b.replay) + '&follow&gallery=' + i + '">Watch</a> <b>' + esc(b.name) + '</b>'
    + ' <span class="when">' + esc(b.world) + ' · ' + (b.samples / 1e6).toFixed(1) + 'M samples, ' + Math.round(b.total / 1e6) + 'M in all' + extra + '</span>'
    + (bits.length ? '<span class="nums">' + esc(bits.join(' · ')) + '</span>' + tested : '') + '</li>';
}
fetch('/replays/gallery/index.json', { cache: 'no-cache' }).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.json();
}).then((g) => {
  let i = 0, html = '';
  const flat = [];
  for (const s of g.steps) {
    html += '<h2>' + esc(s.title) + '</h2>' + (s.text ? '<p>' + esc(s.text) + '</p>' : '') + '<ol class="brains">';
    for (const b of s.brains) html += brain(b, i++);
    html += '</ol>';
  }
  const now = g.training.concat(g.latest);
  if (now.length) {
    html = '<h2>Training now</h2><p>The newest brains from the forks training right now, as they come back from the GPUs they train on.</p><ol class="brains">'
      + now.map((b) => brain(b, i++, b.finished ? ' · finished ' + ago(b.finished) : ' · training')).join('') + '</ol>' + html;
  }
  if (g.asides.length) {
    html += '<h2>On the side</h2><ol class="brains">' + g.asides.map((b) => brain(b, i++).replace('</b>', '</b> <span class="aside">' + esc(b.title) + '</span>')
      .replace('</li>', '<p>' + esc(b.text) + '</p></li>')).join('') + '</ol>';
  }
  // what's being worked on goes first on the page, numbered last so older links still land on the same brain
  let working = '';
  for (const w of g.working || []) {
    if (!w.brains.length) continue;
    working += '<h2>Working on now: ' + esc(w.title) + '</h2><p>' + esc(w.text) + '</p><ol class="brains">'
      + w.brains.map((b) => brain(b, i++).replace('</li>', '<p>' + esc(b.note) + '</p></li>')).join('') + '</ol>';
  }
  html = working + html;
  box.innerHTML = html + '<p class="when">Updated ' + ago(g.updated) + '.</p>';
}).catch(() => {
  box.innerHTML = '<p>The gallery isn’t up right now. The <a href="/watch/">latest brain</a> still plays.</p>';
});
</script>`;
write('brains', page({
  title: 'Brains',
  description: 'Every brain the Terrikins have had, from the first that learned to eat to the ones training now. Watch any of them.',
  path: '/brains/',
  body: `<h1>Brains</h1>
<p>Every brain the one training now came from, back to the first, and a few side experiments. Watch plays one for three minutes in the world it trained in, in the same garden each time. The numbers are its own test results in that world, and the worlds got harder as they went, so they compare within a step more than across them.</p>
<div id="gallery"><p>Loading…</p></div>
${BRAINS}`,
}));
// Terrarium at Home: the page, the reviews of the worker's code (site/reviews/, each a model's review pasted in
// whole, with the commit it read) and the board, read live from the job queue
const atHome = read(join(SITE, 'at-home.md'));
for (const key of ['title', 'description', 'usd_per_billion', 'aud_per_usd', 'aud_date']) {
  if (!atHome.meta[key]) throw new Error(`site/at-home.md has no ${key}`);
}
const reviews = existsSync(join(SITE, 'reviews')) ? readdirSync(join(SITE, 'reviews')).filter((f) => f.endsWith('.md')).sort().reverse().map((f) => {
  const { meta, body } = read(join(SITE, 'reviews', f));
  for (const key of ['model', 'date', 'commit', 'verdict']) {
    if (!meta[key]) throw new Error(`reviews/${f} has no ${key}`);
  }
  return { ...meta, body, slug: f.replace(/\.md$/, '') };
}) : [];
for (const r of reviews) {
  const link = r.link ? ` · <a href="${escape(r.link)}">the conversation</a>` : '';
  write(`at-home/reviews/${r.slug}`, page({
    title: `${r.model} on the worker`,
    description: r.verdict,
    path: `/at-home/reviews/${r.slug}/`,
    body: `<article>\n<h1>${escape(r.model)} on the worker</h1>\n<p class="when">${date(r.date)} · read the code at <a href="${REPO}/tree/${escape(r.commit)}">${escape(r.commit.slice(0, 7))}</a>${link}</p>\n${marked(r.body)}</article>\n<p><a href="/at-home/">Terrarium at Home</a></p>`,
  }));
}
const PROMPT = `Read the code a volunteer's computer runs when they lend it to Terrarium at Home, in https://github.com/MartianRiver/Terrarium: sim/terrarium/worker.py, machine.py, snapshot.py and jobs.py, sim/allowed_signers, and the training it starts (sim/terrarium/train.py). docs/compute.md says what it claims to do.

Tell me plainly: what it does on my computer, what it sends and to whom, whether it could ever run code that isn't public in that repo or that the author didn't sign, and anything that looks unsafe or that the docs leave out. Quote the lines each point rests on. I'm deciding whether to run it on my own PC.`;
const reviewed = (reviews.length
  ? '<ul class="notes">' + reviews.map((r) => `<li><a href="/at-home/reviews/${r.slug}/">${escape(r.model)}</a><span class="when">${date(r.date)} · code at ${escape(r.commit.slice(0, 7))}</span><p>${escape(r.verdict)}</p></li>`).join('') + '</ul>'
  : '')
  + `<p>Don’t take my word for it. ${reviews.length ? 'These are' : 'The best check is'} a model with no stake in it reading the code: paste this into a new chat with Claude or ChatGPT and read what it says.</p>
<details><summary>The prompt</summary><pre>${escape(PROMPT)}</pre></details>`;
const BOARD = `<div id="board"><p>Loading…</p></div>
<script>
const BOARD_URL = 'https://terrarium-jobs.martianriver.com/api/board';
const PER_BILLION = ${Number(atHome.meta.usd_per_billion)}, AUD = ${Number(atHome.meta.aud_per_usd)};
const box = document.getElementById('board');
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const samples = (n) => n >= 1e9 ? (n / 1e9).toFixed(2) + 'G' : (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + 'M';
const money = (usd) => 'A$' + (usd * AUD).toFixed(2) + ' (US$' + usd.toFixed(2) + ')';
fetch(BOARD_URL).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.json();
}).then((b) => {
  // every machine but a rented one costs me nothing, so it's worth what renting its samples would have cost
  const none = { samples: 0, hours: 0, dollars: 0 };
  const free = ['admin', 'trusted', 'donor'].map((k) => b.totals[k] ?? none).reduce((t, k) => ({ samples: t.samples + k.samples, hours: t.hours + k.hours }), none);
  const rented = { ...none, ...b.totals.rented };
  // what rented GPUs have cost a sample so far (the page's own rate until there are any)
  const perBillion = rented.samples ? rented.dollars / rented.samples * 1e9 : PER_BILLION;
  const worth = (n) => n / 1e9 * perBillion;
  let html = '<p class="saved">Machines that cost me nothing, my Mac and the ones lent to me, have trained <b>' + samples(free.samples) + ' samples</b> over '
    + free.hours.toFixed(1) + ' hours: about <b>' + money(worth(free.samples)) + '</b> saved on rented GPU time.</p>'
    + '<p class="saved">Rented GPUs have trained <b>' + samples(rented.samples) + ' samples</b> over ' + rented.hours.toFixed(1)
    + ' hours, for <b>' + money(rented.dollars) + '</b> paid.</p>';
  if (!b.machines.length) {
    box.innerHTML = html + '<p>No machines on it yet.</p>';
    return;
  }
  const gpu = (m) => esc((m.gpu || '–').replace(/^NVIDIA /, '').replace(/^GeForce /, ''));
  // a rented row is named for its GPU, which has a column of its own; on a phone the GPU goes under the name instead
  const machine = (m) => (m.kind === 'rented' ? 'Rented' : esc(m.name)) + '<span class="gpu-under">' + gpu(m) + '</span>';
  const day = (d) => d ? new Date(d + 'T00:00:00Z').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : '–';
  const aud = (usd) => 'A$' + (usd * AUD).toFixed(2);
  const cost = (m) => m.kind === 'rented' ? '<span class="paid">' + aud(m.dollars ?? 0) + ' paid</span>' : '<span class="free">' + aud(worth(m.samples)) + ' saved</span>';
  html += '<div class="board"><table><thead><tr><th>Machine</th><th class="gpu">GPU</th><th class="n">Samples</th><th class="n hours">Hours</th><th class="n">Jobs</th><th class="n">Paid or saved</th><th class="n last">Last active</th></tr></thead><tbody>'
    + b.machines.map((m) => '<tr><td>' + machine(m) + '</td><td class="gpu">' + gpu(m) + '</td><td class="n">' + samples(m.samples)
      + '</td><td class="n hours">' + m.hours.toFixed(1) + '</td><td class="n">' + m.jobs + '</td><td class="n">' + cost(m) + '</td><td class="n last">' + day(m.last_active) + '</td></tr>').join('')
    + '</tbody></table></div>'
    + '<p class="when">Saved is what renting the same samples would have cost, at what my rented GPUs have cost per sample so far: US$' + perBillion.toFixed(2)
    + ' a billion, at A$' + AUD + ' to the US dollar (the ECB’s rate on ${escape(atHome.meta.aud_date)}). It leaves out the power your machine uses. Paid is every rental, setup and idle time included, so a GPU that never got going still cost something.</p>';
  box.innerHTML = html;
}).catch(() => {
  box.innerHTML = '<p>The board isn’t answering right now. The queue may be restarting; try again in a minute.</p>';
});
</script>`;
for (const mark of ['<!-- reviews -->', '<!-- board -->']) {
  if (!atHome.body.includes(mark)) throw new Error(`site/at-home.md has no ${mark}`);
}
write('at-home', page({
  title: atHome.meta.title,
  description: atHome.meta.description,
  path: '/at-home/',
  body: `<article>\n<h1>${escape(atHome.meta.title)}</h1>\n${marked(atHome.body).replace('<!-- reviews -->', () => reviewed).replace('<!-- board -->', () => BOARD)}</article>`,
}));

// a review build shows the gallery as built on this machine (SITE_GALLERY)
if (review && process.env.SITE_GALLERY) cpSync(process.env.SITE_GALLERY, join(out, 'replays', 'gallery'), { recursive: true });

const used = new Set();
for (const n of notes) {
  const mine = new Set();
  const html = marked(embeds(n.body, n, mine));
  // front matter names every clip a post shows, so a review sees them all at a glance
  const listed = new Set((n.clips ?? '').split(',').map((c) => c.trim()).filter(Boolean));
  if ([...mine].sort().join() !== [...listed].sort().join()) {
    throw new Error(`${n.file}: clips: says ${[...listed].join(', ') || 'nothing'}, the post shows ${[...mine].join(', ') || 'none'}`);
  }
  mine.forEach((c) => used.add(c));
  const banner = n.draft && marks ? '<p class="draft-banner">DRAFT: not published. Only the review build shows this.</p>\n' : '';
  write(`blog/${n.slug}`, page({
    title: n.title,
    description: n.summary,
    path: `/blog/${n.slug}/`,
    body: `<article>\n${banner}<h1>${escape(n.title)}${tag(n)}</h1>\n<p class="when">${date(n.date)}${n.stage ? ` · ${escape(n.stage)}` : ''}<br><a href="/how/">Drafted by ${escape(n.drafted)}</a> · edited by ${escape(n.edited)}${date(n.written) !== date(n.date) ? ` · written up ${date(n.written)}` : ''}</p>\n${html}</article>\n<p><a href="/blog/">All the posts</a></p>${html.includes('class="youtube"') ? `\n${YOUTUBE}` : ''}`,
  }));
}

// the blog was called notes at first, and links to those addresses are out there
const forward = (to) => `<!doctype html>
<meta charset="utf-8">
<title>Moved · Terrarium</title>
<link rel="canonical" href="${ORIGIN}${to}">
<meta http-equiv="refresh" content="0; url=${to}">
<script>location.replace('${to}' + location.hash)</script>
<p>This is at <a href="${to}">${to}</a> now.</p>
`;
write('notes', forward('/blog/'));
for (const n of notes) write(`notes/${n.slug}`, forward(`/blog/${n.slug}/`));

writeFileSync(join(out, '404.html'), page({
  title: 'Not here',
  description: 'Nothing at this address.',
  path: '/404.html',
  body: '<h1>Nothing here</h1>\n<p>That page doesn’t exist. Try <a href="/">the start</a> or <a href="/watch/">watching the Terrikins</a>.</p>',
}));
if (review) writeFileSync(join(out, 'robots.txt'), 'User-agent: *\nDisallow: /\n');

for (const f of ['site.css', 'hero.jpg', 'card.jpg', 'fonts']) cpSync(join(SITE, f), join(out, f), { recursive: true });

// clip masters never go in git: each one is cut from the backups folder (SITE_CLIPS) and cached by its settings
if (used.size && !media) throw new Error(`posts show clips (${[...used].join(', ')}): set SITE_CLIPS to the clips folder`);
for (const name of used) {
  const clip = clips[name];
  const src = join(media, clip.from);
  if (!existsSync(src)) throw new Error(`clip ${name}: ${clip.from} isn't in ${media}`);
  const key = createHash('sha256').update(JSON.stringify(clip)).digest('hex').slice(0, 12);
  const cached = join(CACHE, `${name}-${key}`);
  if (!existsSync(`${cached}.mp4`)) {
    mkdirSync(CACHE, { recursive: true });
    const cut = ['-v', 'error', '-y', '-ss', String(clip.start), '-t', String(clip.seconds), '-i', src];
    const frame = `${clip.crop ? `crop=${clip.crop},` : ''}scale=${clip.width}:-2`;
    execFileSync('ffmpeg', [...cut, '-an', '-vf', `${frame},fps=30`, '-c:v', 'libx264', '-preset', 'slow', '-crf', String(clip.crf ?? 26),
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', `${cached}.mp4`]);
    execFileSync('ffmpeg', [...cut, '-frames:v', '1', '-vf', frame, '-q:v', '5', `${cached}.jpg`]);
  }
  mkdirSync(join(out, 'media'), { recursive: true });
  cpSync(`${cached}.mp4`, join(out, 'media', `${name}.mp4`));
  cpSync(`${cached}.jpg`, join(out, 'media', `${name}.jpg`));
}

// the viewer a lent machine runs to watch its own runs (sim/terrarium/watch.py), listed with each file's sha256 and
// fetched as one gzipped bundle: Cloudflare adds its analytics script to HTML on the way, so pages fetched one by one
// never match their sha256
const viewer = join(out, 'at-home', 'viewer');
const own = new Set(['files.json', 'bundle.json.gz']);
if (existsSync(viewer)) {
  const files = {};
  const data = {};
  const walk = (dir) => {
    for (const f of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, f.name);
      const name = relative(viewer, path).split(sep).join('/');
      if (f.isDirectory()) walk(path);
      else if (!own.has(name)) {
        const bytes = readFileSync(path);
        files[name] = createHash('sha256').update(bytes).digest('hex');
        data[name] = bytes.toString('base64');
      }
    }
  };
  walk(viewer);
  const bundle = gzipSync(JSON.stringify({ files: data }), { level: 9 });
  writeFileSync(join(viewer, 'bundle.json.gz'), bundle);
  const digest = createHash('sha256').update(bundle).digest('hex');
  writeFileSync(join(viewer, 'files.json'), JSON.stringify({ files, bundle: digest }, null, 1) + '\n');
}

console.log(`site: ${notes.length} posts${review ? ` (${notes.filter((n) => n.draft).length} drafts)` : ''}, ${used.size} clips → ${out}`);
