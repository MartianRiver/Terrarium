// The kids page's screens around a game: the pictures to pick from (with Big's levels as numbered stones, stars
// under each, locked ones shut, and who you are: a costume, or a Terrikin in a colour), the stars lit as a game goes,
// and how a round went. A stick or the arrow keys move along one row at a time (the game, who, the colour).
import { COLONY_COLOURS } from './palette';
import { key, opened, type Look, type Progress, type Round } from './kidsprogress';

export interface Choice {
  mode: string;
  level: number;
}

// each mode's levels, by their star targets
export type Levels = Record<string, [number, number][]>;
export type Row = 'game' | 'look' | 'colour';

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;
const row = (lit: number) => [0, 1, 2].map((i) => `<i class="${i < lit ? 'on' : ''}">★</i>`).join('');

export class Menu {
  constructor(private levels: Levels, pick: (c: Choice) => void, dress: (look: Look) => void, paint: (colour: number) => void) {
    $('#pick').querySelectorAll<HTMLButtonElement>('[data-mode]').forEach((b) =>
      b.addEventListener('click', () => pick(this.latest(b.dataset.mode!))));
    $('#levels').addEventListener('click', (e) => {
      const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-level]');
      if (b && !b.disabled) pick({ mode: 'big', level: Number(b.dataset.level) });
    });
    document.querySelectorAll<HTMLButtonElement>('[data-look]').forEach((b) =>
      b.addEventListener('click', () => dress(b.dataset.look as Look)));
    document.querySelectorAll<HTMLButtonElement>('[data-colour]').forEach((b) =>
      b.addEventListener('click', () => paint(Number(b.dataset.colour))));
  }

  // the rows a stick moves between: the colours only for a Terrikin
  rows(p: Progress): Row[] {
    return p.look === 'terrikin' ? ['game', 'look', 'colour'] : ['game', 'look'];
  }

  private progress: Progress | null = null;

  // the highest level open in a mode: what its picture starts
  latest(mode: string): Choice {
    return { mode, level: this.progress ? opened(this.progress, mode, this.levels[mode].length) : 1 };
  }

  // everything that can be picked, in order across the screen, for keys and a gamepad
  choices(p: Progress): Choice[] {
    return Object.keys(this.levels).flatMap((mode) =>
      Array.from({ length: opened(p, mode, this.levels[mode].length) }, (_, i) => ({ mode, level: i + 1 })));
  }

  targets(c: Choice): [number, number] {
    return this.levels[c.mode][c.level - 1];
  }

  showPick(p: Progress, chosen: Choice, focus: Row = 'game') {
    this.progress = p;
    $('#pick').dataset.row = focus;
    document.body.style.setProperty('--you', `#${COLONY_COLOURS[p.colour].getHexString()}`);
    $('.colours').hidden = p.look !== 'terrikin';
    document.querySelectorAll<HTMLButtonElement>('[data-colour]').forEach((b) =>
      b.setAttribute('aria-pressed', String(Number(b.dataset.colour) === p.colour)));
    $('#stars-total').textContent = String(p.total);
    document.querySelectorAll<HTMLButtonElement>('#pick [data-mode]').forEach((b) =>
      b.classList.toggle('chosen', b.dataset.mode === chosen.mode));
    const big = this.levels.big ?? [];
    const open = opened(p, 'big', big.length);
    $('#levels').innerHTML = big.map((_, i) => {
      const n = i + 1;
      const locked = n > open;
      const on = chosen.mode === 'big' && chosen.level === n;
      return `<button type="button" data-level="${n}" class="${on ? 'chosen' : ''}" ${locked ? 'disabled' : ''}
        aria-label="Level ${n}${locked ? ', locked' : ''}"><b>${locked ? '🔒' : n}</b><span>${row(p.stars[key('big', n)] ?? 0)}</span></button>`;
    }).join('');
    document.querySelectorAll<HTMLButtonElement>('[data-look]').forEach((b) =>
      b.setAttribute('aria-pressed', String(b.dataset.look === p.look)));
  }

  // the HUD's three stars, lit as the catches pass the level's targets
  goals(catches: number, [two, three]: [number, number]) {
    const lit = catches >= three ? 3 : catches >= two ? 2 : catches > 0 ? 1 : 0;
    const box = $('#goals');
    const html = row(lit);
    if (box.innerHTML !== html) box.innerHTML = html;
    return lit;
  }

  showEnd(catches: number, round: Round, more: boolean) {
    $('#end-count').textContent = String(catches);
    $('#end-stars').innerHTML = row(round.stars);
    $('#end-best').textContent = String(round.best);
    $('#end').classList.toggle('record', round.record);
    const unlocked = $('#end-open');
    unlocked.hidden = round.opened === null;
    unlocked.querySelector('b')!.textContent = String(round.opened ?? '');
    $('#next').hidden = !more;
  }
}
