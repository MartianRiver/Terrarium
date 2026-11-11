# One static HTML page for a folder of balance runs: the gate table, then per setting the nims, standing food, stores,
# births and deaths over time, a thin line for each game and a bold one for the median. Plain SVG, nothing fetched.
#
#   uv run python bench/balance_report.py DIR [DIR ...] [--out report.html]      (reads DIR/balance.json)

import argparse
import html
import json
from pathlib import Path

import numpy as np

W, H = 470, 210
PAD = {'l': 46, 'r': 10, 't': 12, 'b': 34}
BLUE, ORANGE, GREEN, GREY = '#2a6fb0', '#d9730d', '#3c8a3c', '#888'

CSS = """
body{font:14px/1.45 system-ui,sans-serif;margin:24px auto;max-width:1040px;padding:0 16px;color:#222;background:#fff}
h1{font-size:22px} h2{font-size:17px;margin:28px 0 4px} p.note{color:#555;margin:2px 0 10px}
table{border-collapse:collapse;margin:8px 0;font-size:13px} td,th{padding:4px 9px;border-bottom:1px solid #ddd;text-align:right}
td:first-child,th:first-child{text-align:left} .pass{color:#1d7a1d;font-weight:600} .fail{color:#b3261e;font-weight:600}
.row{display:flex;flex-wrap:wrap;gap:6px 14px} figure{margin:0} figcaption{font-size:12px;color:#444;margin-left:46px}
svg text{font:11px system-ui,sans-serif;fill:#444} .night{fill:#00000012} .grid{stroke:#e4e4e4}
@media (prefers-color-scheme:dark){body{background:#181a1d;color:#ddd}p.note,figcaption{color:#aaa}td,th{border-color:#333}
svg text{fill:#bbb}.night{fill:#ffffff14}.grid{stroke:#333}}
"""


def scale(lo: float, hi: float, a: float, b: float):
    return lambda v: a + (v - lo) / ((hi - lo) or 1) * (b - a)


def ticks(hi: float, n: int = 5) -> list[float]:
    step = max(1, int(np.ceil(hi / n)))
    return [i * step for i in range(int(hi // step) + 1)]


def path(xs, ys, fx, fy) -> str:
    return 'M' + ' L'.join(f'{fx(x):.1f},{fy(y):.1f}' for x, y in zip(xs, ys))


def chart(t, lines: list[tuple[np.ndarray, str]], cycle: float, ylabel: str, ymax: float | None = None,
          guide: float | None = None, title: str = '') -> str:
    """lines: (games x samples array, colour): thin per game, bold median. Nights shaded; x in days."""
    days = t[-1] / cycle
    top = ymax if ymax is not None else max(1.0, *(float(np.max(v)) for v, _ in lines)) * 1.08
    fx = scale(0, t[-1], PAD['l'], W - PAD['r'])
    fy = scale(0, top, H - PAD['b'], PAD['t'])
    out = [f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">']
    for d in range(int(np.ceil(days))):
        a, b = (d + 0.5) * cycle, min((d + 1) * cycle, t[-1])
        if a < t[-1]:
            out.append(f'<rect class="night" x="{fx(a):.1f}" y="{PAD["t"]}" width="{fx(b) - fx(a):.1f}" height="{H - PAD["t"] - PAD["b"]}"/>')
    for y in ticks(top):
        out.append(f'<line class="grid" x1="{PAD["l"]}" x2="{W - PAD["r"]}" y1="{fy(y):.1f}" y2="{fy(y):.1f}"/>'
                   f'<text x="{PAD["l"] - 5}" y="{fy(y) + 4:.1f}" text-anchor="end">{y:g}</text>')
    for d in range(int(days) + 1):
        out.append(f'<text x="{fx(d * cycle):.1f}" y="{H - PAD["b"] + 14}" text-anchor="middle">{d}</text>')
    if guide is not None:
        out.append(f'<line x1="{PAD["l"]}" x2="{W - PAD["r"]}" y1="{fy(guide):.1f}" y2="{fy(guide):.1f}" stroke="{GREY}" stroke-dasharray="4 3"/>')
    for v, colour in lines:
        for row in np.atleast_2d(v):
            out.append(f'<path d="{path(t, row, fx, fy)}" fill="none" stroke="{colour}" stroke-width="0.8" opacity="0.35"/>')
        out.append(f'<path d="{path(t, np.median(np.atleast_2d(v), 0), fx, fy)}" fill="none" stroke="{colour}" stroke-width="2.4"/>')
    out.append(f'<text x="{(PAD["l"] + W - PAD["r"]) / 2}" y="{H - 5}" text-anchor="middle">days (the shaded half of each is night)</text>')
    out.append(f'<text transform="translate(11,{H / 2 - 12}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>')
    out.append('</svg>')
    return ''.join(out)


def figure(svg: str, caption: str) -> str:
    return f'<figure>{svg}<figcaption>{caption}</figcaption></figure>'


def gate_table(runs: list[dict]) -> str:
    rows = ['<table><tr><th>setting</th><th>supply ratio</th><th>nims at end</th><th>after day 2</th><th>peak</th>'
            '<th>games extinct</th><th>late trend (nims/day)</th><th>harvest</th><th>verdict</th></tr>']
    for r in runs:
        g, s = r['gates'], r['supply']
        verdict = ('<span class="pass">pass</span>' if g['pass'] else '<span class="fail">fail</span>' if g['pass'] is False
                   else 'incomplete (too few days)' if g.get('status') == 'incomplete' else 'no gate')
        if g['checks']:
            failed = [k for k, v in g['checks'].items() if not v]
            verdict += f' ({g["kind"]}' + (f'; failed: {html.escape(", ".join(failed))}' if failed else '') + ')'
        colonies = f', colonies {g["extinct_colonies"]} of {g["games"] * g["colonies"]}' if 'extinct_colonies' in g else ''
        late = 'needs 4+ days' if g.get('late_slope') is None else f'{g["late_slope"]:+.2f}'
        rows.append(f'<tr><td>{html.escape(r["label"])}</td><td>{s["ratio"]:.2f}</td>'
                    f'<td>{g["end_median"]:.0f} of {g["start"]} ({g["end_share"]:.0%})</td><td>{g["day2_share"]:.0%}</td>'
                    f'<td>{g["peak_median"]:.0f}</td><td>{g["extinct_games"]} of {g["games"]}{colonies}</td><td>{late}</td>'
                    f'<td>{s["harvest"]:.0%}</td><td>{verdict}</td></tr>')
    return ''.join(rows) + '</table>'


def section(r: dict) -> str:
    t = np.array(r['t'])
    s, g = r['supply'], r['gates']
    cycle = s['cycle']
    alive = np.array(r['alive']).sum(-1).T                      # games x samples
    births = np.array(r['births']).sum(-1).T
    deaths = np.array(r['deaths']).sum(-1).T
    food = np.array(r['food']).T
    store = np.array(r['store']).sum(-1).T
    charts = [
        figure(chart(t, [(alive, BLUE)], cycle, 'nims alive', guide=s['start'], title='nims alive'),
               f'nims alive, both colonies (dashed: the {s["start"]} it starts with)'),
        figure(chart(t, [(food, GREEN)], cycle, 'foods standing', title='food standing'),
               f'food standing in the world ({r["dials"]["food_count"]} places grow it; it all goes at nightfall)'),
        figure(chart(t, [(store, ORANGE)], cycle, 'jelly in the stores', title='stores'),
               'jelly in both stores (what the colonies keep for the night and for eggs)'),
        figure(chart(t, [(births, BLUE), (deaths, ORANGE)], cycle, 'nims, running total', title='births and deaths'),
               'blue: hatched so far; orange: died so far'),
    ]
    if r['dials']['meadows']:
        grass = np.array(r['grass']).T
        charts.append(figure(chart(t, [(grass, GREEN)], cycle, 'grass left (share of full)', ymax=1.05, title='grass'),
                             'grass cover left, as a share of what the meadows hold when full'))
    by = r['deaths_by']
    total = sum(by.values()) or 1
    where = ', '.join(f'{k.replace("_", " ")} {v}' for k, v in by.items())
    d = r['dials']
    note = (f'ratio {s["ratio"]:.2f}: {s["grown"]:.0f} foods grown at most a day (+{s["grass"]:.0f} of grass) against {s["need"]:.0f} needed; '
            f'{d["food_count"]} foods, regrow {d["regrow"][0]:.1f} to {d["regrow"][1]:.1f} s, {d["patches"]} patches of radius {d["patch_radius"]:g} m. '
            f'Deaths over all games ({total if by else 0}): {where}; {sum(r["beside_store"])} of them in a nest whose store had jelly. '
            f'Ran {r["world_seconds"]:.0f} world seconds at {r["speed"]:.0f} per wall second, {g["games"]} games at once.')
    return f'<h2>{html.escape(r["label"])}</h2><p class="note">{note}</p><div class="row">{"".join(charts)}</div>'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('dirs', nargs='+', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    runs = [r for d in a.dirs for r in json.loads((d / 'balance.json').read_text())['runs']]
    out = a.out or a.dirs[0] / 'report.html'
    body = ''.join(section(r) for r in runs)
    out.write_text(
        f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Balance test</title><style>{CSS}</style><h1>Does the world hold its nims?</h1>'
        f'<p class="note">Scripted colonies (carrier, nester, a forager that knows the patches) in a world with no end. '
        f'Thin lines are single games, the bold one is the median. The supply ratio is the food the world can grow in a day '
        f'and night divided by what the starting nims eat in it (see bench/balance_supply.py); harvest is the share of that '
        f'growing the colonies actually picked.</p>{gate_table(runs)}{body}')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
