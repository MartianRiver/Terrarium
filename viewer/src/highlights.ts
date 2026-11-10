// The picker's Highlights row: moments worth watching again (a hack, a first, something funny), from the channel's
// index.json `highlights`. Each is one replay played from `from`, looping up to `to`, so a good moment doesn't sink as
// the lines move on. No `highlights` key, no row.
import { CHANNEL } from './pickshared';

export type Kind = 'funny' | 'cool' | 'milestone' | 'exploit';

// replay: a file beside the index (or an absolute path); from/to: seconds into it; follow: the id of the nim the camera
// stays on; cam/look: the camera, as the viewer's &cam= and &look= take it
export interface Highlight {
  title: string; about: string; date: string; kind: Kind | string; replay: string;
  from?: number; to?: number; follow?: number; cam?: string; look?: string; line?: string; game?: string;
}

// cards shown before "more"
export const SHOWN = 8;

export interface Highlights { shown: Highlight[]; rest: Highlight[] }

export function highlightPlan(list: Highlight[] | undefined, shown = SHOWN): Highlights {
  // newest first; the same day keeps the publisher's order
  const sorted = (list ?? []).map((h, i) => ({ h, i })).sort((a, b) => b.h.date.localeCompare(a.h.date) || a.i - b.i).map((x) => x.h);
  return { shown: sorted.slice(0, shown), rest: sorted.slice(shown) };
}

const dir = CHANNEL.slice(0, CHANNEL.lastIndexOf('/') + 1);

export function highlightHref(h: Highlight) {
  const q = [`replay=${dir && !h.replay.startsWith('/') ? dir : ''}${h.replay}`, `name=${encodeURIComponent(h.title)}`];
  if (h.from) q.push(`from=${h.from}`);
  if (h.to) q.push(`to=${h.to}`);
  if (h.follow !== undefined) q.push('follow', `pick=${h.follow}`);
  if (h.cam) q.push(`cam=${encodeURIComponent(h.cam)}`);
  if (h.look) q.push(`look=${h.look}`);
  return `/watch/?${q.join('&')}`;
}
