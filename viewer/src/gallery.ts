// The site's gallery of brains (/brains/, from terrarium.gallery): a replay opened from it carries &gallery=N, its
// place in the gallery, and gets a bar to step to the brain before or after it without going back to the list.

import { createLogger } from './lib/logger';

const log = createLogger('gallery');
const INDEX = '/replays/gallery/index.json';

interface Brain { name: string; replay: string; world: string; samples: number; total: number }
interface Index { steps: { title: string; brains: Brain[] }[]; training: Brain[]; latest: Brain[]; asides: (Brain & { title: string })[] }

// the same order the brains page numbers them in
export function flatten(g: Index): { brain: Brain; group: string }[] {
  return [
    ...g.steps.flatMap((s) => s.brains.map((brain) => ({ brain, group: s.title }))),
    ...[...g.training, ...g.latest].map((brain) => ({ brain, group: 'Training now' })),
    ...g.asides.map((brain) => ({ brain, group: brain.title })),
  ];
}

function link(i: number, all: ReturnType<typeof flatten>, text: string) {
  const a = document.createElement('a');
  a.textContent = text;
  const params = new URLSearchParams(location.search);
  params.set('replay', `/replays/gallery/${all[i].brain.replay}`);
  params.set('gallery', String(i));
  a.href = `${location.pathname}?${params}`.replace(/%2F/g, '/');
  a.setAttribute('aria-label', `${text === '◀' ? 'Previous' : 'Next'} brain: ${all[i].brain.name}`);
  return a;
}

export async function galleryBar(at: number) {
  try {
    const res = await fetch(INDEX, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`${res.status}`);
    const all = flatten((await res.json()) as Index);
    const here = all[at];
    if (!here) return;
    const bar = document.createElement('nav');
    bar.id = 'gallery';
    bar.setAttribute('aria-label', 'Brains');
    if (at > 0) bar.append(link(at - 1, all, '◀'));
    const what = document.createElement('span');
    what.textContent = `${here.group}: ${here.brain.name} · ${here.brain.world} · ${Math.round(here.brain.total / 1e6)}M samples in all · ${at + 1} of ${all.length}`;
    bar.append(what);
    if (at < all.length - 1) bar.append(link(at + 1, all, '▶'));
    const list = document.createElement('a');
    list.href = '/brains/';
    list.textContent = 'All brains';
    bar.append(list);
    document.body.append(bar);
  } catch (err) {
    // the replay still plays; only the stepping is missing
    log.warn('no gallery bar', { error: String(err) });
  }
}
