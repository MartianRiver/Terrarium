// helpers the picker's plans share: the channel's address, a link into the watch page, short dates and sentences
export const CHANNEL = '/replays/nursery/index.json';

export function sentence(text = '') {
  const end = text.search(/[.!?](\s|$)/);
  return end < 0 ? text : text.slice(0, end + 1);
}

export function when(iso: string, now: number) {
  const d = new Date(iso);
  const today = new Date(now).toDateString() === d.toDateString();
  return today ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

export const watch = (keys: string[], start?: string, at?: string) =>
  `/watch/?channel=${CHANNEL}&game=${keys.map(encodeURIComponent).join(',')}${start ? `&start=${encodeURIComponent(start)}` : ''}${at ? `&at=${encodeURIComponent(at)}` : ''}`;

// each run's title is "Game · arm · seed 1 · 22.1M samples so far": the arm names the row, the rest is its note
export function runRow(item: { title: string; replay: string }, key: string) {
  const [, arm = '', ...rest] = item.title.split(' · ');
  return { title: arm, text: '', href: watch([key], item.replay), note: rest.join(' · ') };
}
