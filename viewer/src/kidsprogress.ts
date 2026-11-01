// How a child is getting on at Catch them!, kept in this browser: stars for each level (one for any catch, two and
// three for the level's targets), the best catch count, the stars caught in all, who they are (a Terrikin in a colour,
// or a costume). Two stars on a level opens the next.

export const LOOKS = ['terrikin', 'dino', 'dragon', 'panda', 'penguin', 'cheetah'] as const;
export type Look = (typeof LOOKS)[number];
// a Terrikin can be any colony's colour but the runners' (colony 0)
export const COLOURS = [1, 2, 3] as const;

export interface Progress {
  best: Record<string, number>;
  stars: Record<string, number>;
  total: number;
  rounds: number;
  look: Look;
  colour: number;
}

export interface Round {
  stars: number;
  best: number;
  record: boolean;
  // the level this round opened, if it opened one
  opened: number | null;
}

const KEY = 'terrarium.kids.progress';
const OPENS = 2;

export const key = (mode: string, level: number) => `${mode}:${level}`;

export function fresh(): Progress {
  return { best: {}, stars: {}, total: 0, rounds: 0, look: 'terrikin', colour: COLOURS[0] };
}

export function load(): Progress {
  try {
    const got = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    // a costume or colour this page doesn't have (yet, or any more) is the plain one
    return {
      ...fresh(), ...got,
      look: LOOKS.includes(got.look) ? got.look : 'terrikin',
      colour: (COLOURS as readonly number[]).includes(got.colour) ? got.colour : COLOURS[0],
    };
  } catch {
    return fresh();
  }
}

export function save(p: Progress) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    // a private window: not kept, the game still plays
  }
}

export function starsFor(catches: number, [two, three]: [number, number]): number {
  return catches >= three ? 3 : catches >= two ? 2 : catches > 0 ? 1 : 0;
}

// levels open from 1, each after two stars on the one before
export function opened(p: Progress, mode: string, levels: number): number {
  let n = 1;
  while (n < levels && (p.stars[key(mode, n)] ?? 0) >= OPENS) n++;
  return n;
}

export function record(p: Progress, mode: string, level: number, levels: number, catches: number, targets: [number, number]): [Progress, Round] {
  const k = key(mode, level);
  const stars = starsFor(catches, targets);
  const before = opened(p, mode, levels);
  const best = p.best[k] ?? 0;
  const next: Progress = {
    ...p,
    best: { ...p.best, [k]: Math.max(best, catches) },
    stars: { ...p.stars, [k]: Math.max(p.stars[k] ?? 0, stars) },
    total: p.total + catches,
    rounds: p.rounds + 1,
  };
  const after = opened(next, mode, levels);
  return [next, { stars, best: Math.max(best, catches), record: catches > best && catches > 0, opened: after > before ? after : null }];
}
