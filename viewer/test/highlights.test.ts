import { describe, expect, it } from 'vitest';
import { highlightHref, highlightPlan, SHOWN, type Highlight } from '../src/highlights';

const hl = (title: string, date: string, more: Partial<Highlight> = {}): Highlight => ({ title, about: 'x', date, kind: 'funny', replay: `${title}.jsonl.gz`, ...more });

describe('the highlights row', () => {
  it('puts the newest first, keeping the order of the same day', () => {
    const { shown } = highlightPlan([hl('a', '2026-11-01'), hl('b', '2026-11-05'), hl('c', '2026-11-05'), hl('d', '2026-10-29')]);
    expect(shown.map((h) => h.title)).toEqual(['b', 'c', 'a', 'd']);
  });

  it('shows the first few and leaves the rest behind "more"', () => {
    const list = Array.from({ length: SHOWN + 3 }, (_, i) => hl(`h${i}`, `2026-11-${String(i + 1).padStart(2, '0')}`));
    const { shown, rest } = highlightPlan(list);
    expect(shown).toHaveLength(SHOWN);
    expect(rest.map((h) => h.title)).toEqual(['h2', 'h1', 'h0']);
  });

  it('is empty without a highlights key', () => {
    expect(highlightPlan(undefined)).toEqual({ shown: [], rest: [] });
  });

  it('links to the replay beside the index, from its start second, following one nim', () => {
    const href = highlightHref(hl('hole', '2026-11-01', { from: 20, to: 56, follow: 5, replay: 'hl-hole.jsonl.gz' }));
    expect(href).toBe('/watch/?replay=/replays/nursery/hl-hole.jsonl.gz&name=hole&from=20&to=56&follow&pick=5');
  });

  it('leaves out what a highlight doesn’t say, and keeps an absolute replay path as it is', () => {
    const href = highlightHref(hl('a b', '2026-11-01', { replay: '/replays/x.jsonl.gz', cam: 'wide', look: '0.8,-0.5,0' }));
    expect(href).toBe('/watch/?replay=/replays/x.jsonl.gz&name=a%20b&cam=wide&look=0.8,-0.5,0');
  });
});
