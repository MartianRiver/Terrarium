// m:ss, then h:mm:ss, then 2d 03:15:09, for a world that runs for days
export function clock(seconds: number) {
  const s = Math.floor(seconds);
  const pad = (n: number) => String(n).padStart(2, '0');
  const [d, h, m] = [Math.floor(s / 86400), Math.floor((s % 86400) / 3600), Math.floor((s % 3600) / 60)];
  if (d) return `${d}d ${pad(h)}:${pad(m)}:${pad(s % 60)}`;
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
