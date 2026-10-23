// Small SVG line charts for the runs page: one measure each, all on the same
// samples axis, so hovering any of them shows that update on every chart.

const SVG = 'http://www.w3.org/2000/svg';
const W = 320;
const H = 150;
const PAD = { left: 48, right: 44, top: 10, bottom: 22 };

export interface Series {
  name: string;
  values: (number | null)[];
}

export interface Chart {
  el: HTMLElement;
  show(i: number | null): void;
}

function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

function niceStep(raw: number) {
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
}

function ticks(lo: number, hi: number) {
  if (lo === hi) [lo, hi] = [lo - 1, hi + 1];
  const step = niceStep((hi - lo) / 3);
  const out = [];
  for (let t = Math.floor(lo / step) * step; t < hi + step / 2; t += step) out.push(Number(t.toPrecision(12)));
  // as many decimals as the step needs, so neighbouring ticks never read the same
  const label = (t: number) => (step >= 1000 ? compact(t) : t.toFixed(Math.max(0, -Math.floor(Math.log10(step)))));
  return { values: out, label };
}

export function compact(v: number) {
  const a = Math.abs(v);
  if (a >= 1e6) return `${Number((v / 1e6).toPrecision(3))}M`;
  if (a >= 1e3) return `${Number((v / 1e3).toPrecision(3))}k`;
  return String(Number(v.toPrecision(a === 0 || a >= 1 ? 3 : 2)));
}

// the nearest index in a sorted array
function nearest(xs: number[], x: number) {
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] < x) lo = mid;
    else hi = mid;
  }
  return x - xs[lo] < xs[hi] - x ? lo : hi;
}

export function lineChart(title: string, xs: number[], series: Series[], onHover: (i: number | null) => void): Chart {
  const el = document.createElement('figure');
  el.className = 'chart';
  const caption = document.createElement('figcaption');
  caption.textContent = title;
  el.append(caption);
  if (series.length > 1) {
    const legend = document.createElement('div');
    legend.className = 'legend';
    series.forEach((s, k) => {
      const key = document.createElement('span');
      key.innerHTML = `<i class="key s${k + 1}"></i>`;
      key.append(s.name);
      legend.append(key);
    });
    el.append(legend);
  }

  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  if (!all.length) {
    const none = document.createElement('p');
    none.className = 'none';
    none.textContent = 'Nothing yet.';
    el.append(none);
    return { el, show: () => {} };
  }
  const yt = ticks(Math.min(...all), Math.max(...all));
  const [y0, y1] = [yt.values[0], yt.values[yt.values.length - 1]];
  const x1 = xs[xs.length - 1] || 1;
  const px = (x: number) => PAD.left + (x / x1) * (W - PAD.left - PAD.right);
  const py = (y: number) => H - PAD.bottom - ((y - y0) / (y1 - y0 || 1)) * (H - PAD.top - PAD.bottom);

  const plot = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${title}, by samples trained` });
  for (const t of yt.values) {
    plot.append(svg('line', { class: 'grid', x1: PAD.left, x2: W - PAD.right, y1: py(t), y2: py(t) }));
    const label = svg('text', { class: 'tick', x: PAD.left - 6, y: py(t) + 3, 'text-anchor': 'end' });
    label.textContent = yt.label(t);
    plot.append(label);
  }
  const xStep = niceStep(x1 / 4);
  for (let x = 0; x <= x1; x += xStep) {
    const label = svg('text', { class: 'tick', x: px(x), y: H - 6, 'text-anchor': x ? 'middle' : 'start' });
    label.textContent = compact(x);
    plot.append(label);
  }

  const ends = series.map((s) => {
    let last = s.values.length - 1;
    while (last >= 0 && s.values[last] === null) last--;
    return last;
  });
  // labels at the line ends, unless the lines finish too close to tell apart (the legend has them)
  const endYs = ends.map((last, k) => (last >= 0 ? py(series[k].values[last]!) : NaN));
  const labelEnds = series.length > 1 && endYs.every((y, k) => endYs.every((o, j) => j === k || Math.abs(y - o) >= 11));
  series.forEach((s, k) => {
    // a gap where there's no value (an update in which no episode finished)
    let d = '';
    let pen = 'M';
    s.values.forEach((v, i) => {
      if (v === null) return void (pen = 'M');
      d += `${pen}${px(xs[i]).toFixed(1)},${py(v).toFixed(1)}`;
      pen = 'L';
    });
    plot.append(svg('path', { class: `line s${k + 1}`, d }));
    const last = ends[k];
    if (labelEnds && last >= 0) {
      const label = svg('text', { class: 'end-label', x: px(xs[last]) + 5, y: py(s.values[last]!) + 3 });
      label.textContent = s.name;
      plot.append(label);
    }
  });

  const cross = svg('line', { class: 'cross', y1: PAD.top, y2: H - PAD.bottom, visibility: 'hidden' });
  const dots = series.map((_, k) => svg('circle', { class: `dot s${k + 1}`, r: 4, visibility: 'hidden' }));
  plot.append(cross, ...dots);
  el.append(plot);

  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.hidden = true;
  el.append(tip);

  plot.addEventListener('pointermove', (e) => {
    const box = plot.getBoundingClientRect();
    const x = (((e.clientX - box.left) / box.width) * W - PAD.left) / (W - PAD.left - PAD.right);
    onHover(nearest(xs, Math.max(0, x) * x1));
  });
  plot.addEventListener('pointerleave', () => onHover(null));

  function show(i: number | null) {
    const off = i === null;
    tip.hidden = off;
    cross.setAttribute('visibility', off ? 'hidden' : 'visible');
    if (off) return dots.forEach((d) => d.setAttribute('visibility', 'hidden'));
    const x = px(xs[i]);
    cross.setAttribute('x1', String(x));
    cross.setAttribute('x2', String(x));
    const values = series.map((s, k) => {
      const v = s.values[i];
      dots[k].setAttribute('visibility', v === null ? 'hidden' : 'visible');
      if (v !== null) {
        dots[k].setAttribute('cx', String(x));
        dots[k].setAttribute('cy', String(py(v)));
      }
      return `${series.length > 1 ? `${s.name} ` : ''}${v === null ? '–' : compact(v)}`;
    });
    // in the title row, so it never covers the lines
    tip.textContent = `${compact(xs[i])}: ${values.join(' · ')}`;
  }

  return { el, show };
}
