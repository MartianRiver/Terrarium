import { describe, expect, it } from 'vitest';
import { runReplay, stops } from '../src/learns';

const ck = (...samples: number[]) => samples.map((s) => ({ file: `${String(s).padStart(11, '0')}.pt`, samples: s }));

describe('the brain as it learns', () => {
  it('goes from random moves and the start to a quarter, half and now', () => {
    const got = stops(ck(0, 1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000, 6_000_000, 7_000_000, 8_000_000));
    expect(got.map((s) => s.label)).toEqual(['random moves', 'start', '2M', '4M', 'now · 8M']);
  });

  it('has no start for a run saved before there was one, and no repeats when checkpoints are few', () => {
    expect(stops(ck(4_000_000)).map((s) => s.label)).toEqual(['random moves', 'now · 4M']);
    expect(stops(ck(2_000_000, 4_000_000)).map((s) => s.label)).toEqual(['random moves', '2M', 'now · 4M']);
    expect(stops([]).map((s) => s.label)).toEqual(['random moves']);
  });

  it('only reads run replays', () => {
    expect(runReplay(new URL('http://x/api/runs/20261101-1-a/replay/00000000000.pt?seed=3'))).toEqual(
      { id: '20261101-1-a', file: '00000000000.pt', seed: '3' });
    expect(runReplay(new URL('http://x/replays/gallery/a.jsonl.gz'))).toBeNull();
    expect(runReplay(null)).toBeNull();
  });
});
