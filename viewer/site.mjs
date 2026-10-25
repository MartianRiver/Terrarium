// Builds the public site's pages from ../site into OUT, next to the viewer at OUT/watch/.
// node site.mjs OUT [--review [--marked]]   (SITE_CLIPS=DIR: the clips backups folder, when a post shows a clip)
// --review adds the drafts (SITE_DRAFTS, or site/drafts/; never committed) and keeps search engines out. They look
// exactly as they will when published, unless --marked adds a review bar, DRAFT tags and where each clip came from.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
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

function date(iso) {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
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
    <a href="/notes/">Notes</a>
    <a href="${REPO}">Code</a>
  </nav>
</header>
<main${wide ? ' class="wide"' : ''}>
${body}
</main>
<footer>
  <p>Made by River James (Martian River). <a href="${INSTAGRAM}">Instagram</a> · <a href="${REPO}">GitHub</a> · MIT licence. No cookies, no tracking.</p>
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
    for (const key of ['title', 'date', 'summary']) {
      if (!meta[key]) throw new Error(`${f} has no ${key}`);
    }
    return { ...meta, file: f, slug: f.replace(/^\d{4}-\d{2}-\d{2}-/, '').replace(/\.md$/, ''), body, draft };
  });
}

const notes = [...posts(join(SITE, 'notes'), false), ...(review ? posts(process.env.SITE_DRAFTS ?? join(SITE, 'drafts'), true) : [])]
  .sort((a, b) => b.date.localeCompare(a.date));
const tag = (n) => (n.draft && marks ? ' <span class="draft">DRAFT</span>' : '');

const list = (items) =>
  `<ul class="notes">\n${items
    .map((n) => `<li><a href="/notes/${n.slug}/">${escape(n.title)}</a>${tag(n)}
  <span class="when">${date(n.date)}</span><p>${escape(n.summary)}</p></li>`)
    .join('\n')}\n</ul>`;

const home = read(join(SITE, 'index.md'));
const hero = `<section class="hero">
  <img src="/hero.jpg" width="1600" height="900" alt="A garden under a glass dome on a red plain. On the lawn inside, little round Terrikins in three colours gather berries around their nests.">
  <div class="pitch">
    <h1>Terrarium</h1>
    <p>${escape(home.meta.tagline)}</p>
    <a class="watch" href="/watch/">Watch them</a>
  </div>
</section>
<script>if (location.search) location.replace('/watch/' + location.search)</script>`;
const latest = notes.length ? `${list(notes.slice(0, 3))}\n<p><a href="/notes/">All the notes</a></p>` : '<p>Nothing written up yet.</p>';
write('', page({
  title: 'Terrarium',
  description: home.meta.description,
  path: '/',
  wide: true,
  body: `${hero}\n<div class="text">\n${marked(home.body).replace('<!-- notes -->', latest)}</div>`,
}));

write('notes', page({
  title: 'Notes',
  description: 'Write-ups of what I tried, what worked and what didn’t.',
  path: '/notes/',
  body: `<h1>Notes</h1>\n<p>What I tried, what worked, what didn’t and what I tried next. The full lab record, every run and dead end, is in the repo’s <a href="${REPO}/tree/main/docs/notes">docs/notes</a>.</p>\n${list(notes)}`,
}));

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
  write(`notes/${n.slug}`, page({
    title: n.title,
    description: n.summary,
    path: `/notes/${n.slug}/`,
    body: `<article>\n${banner}<h1>${escape(n.title)}${tag(n)}</h1>\n<p class="when">${date(n.date)}${n.stage ? ` · ${escape(n.stage)}` : ''}</p>\n${html}</article>\n<p><a href="/notes/">All the notes</a></p>${html.includes('class="youtube"') ? `\n${YOUTUBE}` : ''}`,
  }));
}

writeFileSync(join(out, '404.html'), page({
  title: 'Not here',
  description: 'Nothing at this address.',
  path: '/404.html',
  body: '<h1>Nothing here</h1>\n<p>That page doesn’t exist. Try <a href="/">the start</a> or <a href="/watch/">watching the Terrikins</a>.</p>',
}));
if (review) writeFileSync(join(out, 'robots.txt'), 'User-agent: *\nDisallow: /\n');

for (const f of ['site.css', 'hero.jpg', 'card.jpg']) cpSync(join(SITE, f), join(out, f));

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

console.log(`site: ${notes.length} notes${review ? ` (${notes.filter((n) => n.draft).length} drafts)` : ''}, ${used.size} clips → ${out}`);
