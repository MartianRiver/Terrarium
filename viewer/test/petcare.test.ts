import { describe, expect, test } from 'vitest';
import { advance, care, hatch, HOUR, mood, nextAt, readCare, stage } from '../src/petcare';

// local clock times, so the sleep window tests don't depend on the machine's zone
const at = (h: number, m = 0, day = 15) => new Date(2027, 0, day, h, m).getTime();
const START = at(10);

describe('persistent pet care', () => {
  test('a meal becomes persistent mess while closed, until the owner cleans it', () => {
    const pet = hatch(START);
    expect(care(pet, 'feed').ok).toBe(true);
    expect(pet.fullness).toBe(85);
    const reopened = readCare(JSON.stringify(pet));
    advance(reopened, START + HOUR);
    expect(reopened.fullness).toBeCloseTo(75);
    expect(reopened.mess).toHaveLength(1);
    const savedMess = structuredClone(reopened.mess);
    advance(reopened, START + 6 * HOUR);
    expect(reopened.mess).toEqual(savedMess);
    expect(reopened.health).toBeLessThan(100);
    expect(care(reopened, 'clean').ok).toBe(true);
    expect(reopened.mess).toEqual([]);
    expect(reopened.health).toBe(100);
  });

  test('offline catch-up matches frequent visits across sleep, illness and digestion', () => {
    const pet = hatch(START);
    care(pet, 'feed');
    advance(pet, START + 0.1 * HOUR);
    care(pet, 'feed');
    advance(pet, START + 2 * HOUR);
    care(pet, 'feed');
    const closed = structuredClone(pet), open = structuredClone(pet);
    const end = START + 30 * HOUR;
    advance(closed, end);
    for (let t = open.updated + 57_713; t < end; t += 57_713) advance(open, t);
    advance(open, end);
    expect(closed.sick).toBe(true);
    for (const key of ['fullness', 'happiness', 'health'] as const) expect(open[key]).toBeCloseTo(closed[key], 7);
    for (const key of ['neglect', 'sickFor'] as const) expect(Math.abs(open[key] - closed[key])).toBeLessThan(10);
    expect(open.sick).toBe(closed.sick);
    expect(open.dead).toBe(closed.dead);
    expect(open.mess).toEqual(closed.mess);
    expect(open.meals).toEqual(closed.meals);
    expect(open.history.map(h => h.text)).toEqual(closed.history.map(h => h.text));
  });

  test('old clock readings neither rewind care nor repeat digestion', () => {
    const pet = hatch(START);
    care(pet, 'feed');
    advance(pet, START + HOUR);
    const expected = structuredClone(pet);
    advance(pet, START - HOUR);
    advance(pet, Number.NaN);
    advance(pet, START + HOUR);
    expect(pet).toEqual(expected);
  });

  test('attention helps but clicking repeatedly cannot instantly refill happiness', () => {
    const pet = hatch(START);
    advance(pet, START + 3 * HOUR);
    const unhappy = pet.happiness;
    expect(care(pet, 'play').ok).toBe(true);
    expect(pet.happiness).toBeCloseTo(unhappy + 18);
    expect(care(pet, 'play').ok).toBe(false);
    expect(care(pet, 'stroke').ok).toBe(true);
    expect(care(pet, 'stroke').ok).toBe(false);
    advance(pet, pet.updated + 60_000);
    expect(care(pet, 'play').ok).toBe(true);
  });

  test('full pets refuse another meal without adding digestion events', () => {
    const pet = hatch(START);
    pet.fullness = 90;
    expect(care(pet, 'feed').ok).toBe(false);
    expect(pet.meals).toEqual([]);
  });

  test('demo time survives closing and real time still advances afterwards', () => {
    const pet = hatch(START);
    care(pet, 'feed');
    pet.offset = HOUR;
    advance(pet, START + pet.offset);
    const reopened = readCare(JSON.stringify(pet));
    advance(reopened, START + HOUR + reopened.offset);
    expect(reopened.updated).toBe(START + 2 * HOUR);
    expect(reopened.fullness).toBeCloseTo(65);
    expect(reopened.mess).toHaveLength(1);
  });

  test('corrupt and incompatible saves fail rather than silently replacing a pet', () => {
    for (const bad of ['{', 'null', '{}', JSON.stringify({ ...hatch(START), version: 2 }),
      JSON.stringify({ ...hatch(START), fullness: -1 }),
      JSON.stringify({ ...hatch(START), bed: 'late' }),
      JSON.stringify({ ...hatch(START), dead: 1 }),
      JSON.stringify({ ...hatch(START), mess: [null] })]) {
      expect(() => readCare(bad)).toThrow();
    }
    expect(readCare(JSON.stringify(hatch(START)))).toEqual(hatch(START));
  });
});

describe('sleep, illness and death', () => {
  test('a night away: fed and tidy at 19:00, opened at 08:00, slower needs and healthy', () => {
    const pet = hatch(at(19));
    care(pet, 'feed');
    advance(pet, at(19, 45));
    care(pet, 'clean');
    advance(pet, at(8, 0, 16));
    // 1 h + 30 min awake at 10/h, 11.5 h asleep at 1/h
    expect(pet.fullness).toBeCloseTo(85 - 10 - 11.5 - 5, 3);
    expect(stage(pet)).toBe('well');
    expect(pet.health).toBe(100);
  });

  test('a school day: full at 07:30 is hungry, not ill, by 15:30', () => {
    const pet = hatch(at(7, 30));
    pet.fullness = 100; pet.happiness = 100;
    advance(pet, at(15, 30));
    expect(pet.fullness).toBeCloseTo(20, 3);
    advance(pet, at(15, 40));
    expect(mood(pet)).toBe('Hungry');
    expect(stage(pet)).toBe('well');
    expect(pet.sick).toBe(false);
  });

  test('away 30 h over a night: asleep part slow, then hungry, then ill', () => {
    const pet = hatch(at(14));
    pet.fullness = 100; pet.happiness = 100;
    advance(pet, at(7, 30, 16));
    expect(pet.fullness).toBeCloseTo(100 - 60 - 11.5, 3);
    advance(pet, at(20, 0, 16));
    expect(pet.fullness).toBe(0);
    expect(pet.sick).toBe(true);
    expect(pet.dead).toBe(false);
  });

  // from 10:00: ill 18:00, asleep 20:00-07:30 at a tenth, very ill ~10:20, dead ~16:20 the next day
  test('neglected from the start of a day: ill after 8 h, slow overnight, dead the next afternoon', () => {
    const pet = hatch(START);
    pet.fullness = 0; pet.happiness = 0;
    advance(pet, START + 4.1 * HOUR);
    expect(stage(pet)).toBe('poorly');
    advance(pet, START + 8.1 * HOUR);
    expect(stage(pet)).toBe('ill');
    expect(mood(pet)).toMatch(/Ill/);
    advance(pet, START + 21.4 * HOUR);
    expect(stage(pet)).toBe('ill');
    advance(pet, START + 24.5 * HOUR);
    expect(stage(pet)).toBe('very ill');
    advance(pet, START + 30.2 * HOUR);
    expect(pet.dead).toBe(false);
    advance(pet, START + 30.5 * HOUR);
    expect(pet.dead).toBe(true);
    expect(pet.health).toBe(0);
    expect(pet.history[0].text).toMatch(/Thank you/);
  });

  test('a poop left overnight and a hungry bedtime are not an illness by morning', () => {
    const pet = hatch(at(19, 30));
    pet.fullness = 0;
    care(pet, 'stroke');
    pet.mess.push({ id: 99, x: 1, y: 0 });
    advance(pet, at(19, 30) + 12 * HOUR);
    expect(pet.sick).toBe(false);
    expect(stage(pet)).toBe('well');
  });

  test('the dead stay put: no care, no more time', () => {
    const pet = hatch(START);
    pet.fullness = 0; pet.happiness = 0;
    advance(pet, START + 31 * HOUR);
    expect(pet.dead).toBe(true);
    const frozen = structuredClone(pet);
    advance(pet, START + 50 * HOUR);
    for (const a of ['feed', 'clean', 'play', 'stroke', 'medicine'] as const) expect(care(pet, a).ok).toBe(false);
    expect(pet).toEqual(frozen);
    expect(readCare(JSON.stringify(pet)).dead).toBe(true);
  });

  test('ill after about 10 h of neglect, and medicine makes it well', () => {
    const pet = hatch(START);
    pet.fullness = 0;
    advance(pet, START + 10 * HOUR);
    expect(pet.sick).toBe(true);
    care(pet, 'feed');
    expect(pet.sick).toBe(true);
    const ok = care(pet, 'medicine');
    expect(ok.ok).toBe(true);
    expect(stage(pet)).toBe('well');
    expect(pet.health).toBe(100);
    expect(care(pet, 'medicine').ok).toBe(false);
    advance(pet, pet.updated + 5 * HOUR);
    expect(pet.dead).toBe(false);
    expect(pet.sick).toBe(false);
  });

  test('a dropping left alone counts as neglect; cleaning in time resets it', () => {
    const pet = hatch(START);
    care(pet, 'feed');
    advance(pet, START + 5 * HOUR);
    expect(pet.neglect).toBeGreaterThan(4 * HOUR);
    care(pet, 'clean');
    expect(pet.neglect).toBe(0);
    advance(pet, START + 5.5 * HOUR);
    const idle = hatch(START);
    care(idle, 'feed');
    advance(idle, START + 18.6 * HOUR);
    expect(idle.sick).toBe(true);
  });

  test('asleep refuses feeding, play and attention; medicine and tidying still work', () => {
    const pet = hatch(at(21));
    for (const a of ['feed', 'play', 'stroke'] as const) {
      const r = care(pet, a);
      expect(r.ok).toBe(false);
      expect(r.text).toMatch(/asleep until 07:30/);
    }
    expect(mood(pet)).toBe('Asleep');
    pet.mess = [{ id: 1, x: 0, y: 0 }];
    expect(care(pet, 'clean').ok).toBe(true);
    pet.sick = true;
    expect(care(pet, 'medicine').ok).toBe(true);
    advance(pet, at(7, 31, 16));
    expect(care(pet, 'feed').ok).toBe(true);
  });

  test('a save from before the care rules loads with a day and a night filled in', () => {
    const old: Record<string, unknown> = { ...hatch(START) };
    for (const k of ['bed', 'wake', 'neglect', 'sick', 'sickFor', 'dead', 'died']) delete old[k];
    const pet = readCare(JSON.stringify(old));
    expect(pet.bed).toBe(1200);
    expect(pet.wake).toBe(450);
    expect(pet.sick).toBe(false);
    expect(pet.dead).toBe(false);
    advance(pet, START + HOUR);
    expect(pet.updated).toBe(START + HOUR);
  });

  test('nextAt gives the next local time of day, today or tomorrow', () => {
    expect(nextAt(at(10), 20 * 60)).toBe(at(20));
    expect(nextAt(at(21), 20 * 60)).toBe(at(20, 0, 16));
    expect(nextAt(at(20), 20 * 60)).toBe(at(20, 0, 16));
    expect(nextAt(at(10), 7.5 * 60)).toBe(at(7, 30, 16));
  });
});
