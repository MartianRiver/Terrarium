# Sound for a reel, placed on the frames its script renders: world sounds from the replays the clips were cut from
# (food vanishing beside a blob, a store growing, a death), only for what's on screen; a sound when a label appears
# and before each cut; ambience by day and by night from the replay's light; music under it all.
# ../sim/.venv/bin/python reel/sound.py reel/0.3.json OUT garden --sounds DIR
#   (a profile in reel/sound.json; sounds are found by file stem under DIR; OUT has build.py's video;
#   writes OUT/<profile>.wav and OUT/<profile>.mp4 and prints each layer's level, so the balance can be checked)
import argparse
import gzip
import json
import random
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

RATE, FPS, TICK_HZ = 48000, 30, 20
VIEWER = Path(__file__).resolve().parents[1]
RUNS = VIEWER.parent / 'runs'
CLOSE = 3.5  # metres around the followed blob that the close-up shows


def db(d):
    return 10 ** (d / 20)


def decode(path, lowpass=None):
    args = ['ffmpeg', '-loglevel', 'error', '-i', str(path)]
    if lowpass:
        args += ['-af', f'lowpass=f={lowpass}']
    raw = subprocess.run(args + ['-f', 'f32le', '-ac', '2', '-ar', str(RATE), '-'], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.float32).reshape(-1, 2)
    return a / max(1e-6, float(np.abs(a).max()))


class Sounds:
    def __init__(self, root):
        self.root, self.cache = Path(root), {}

    def find(self, name):
        hits = list(self.root.rglob(name + '.*'))
        if not hits:
            raise SystemExit(f'no sound {name} under {self.root}')
        return hits[0]

    def get(self, name, lowpass=None):
        """A short sound, starting where it starts (files often lead with silence, which reads as lag)."""
        if (name, lowpass) not in self.cache:
            a = decode(self.find(name), lowpass)
            start = int(np.argmax(np.abs(a).max(axis=1) > 0.05))
            self.cache[name, lowpass] = a[max(0, start - RATE // 200):]
        return self.cache[name, lowpass]

    def bed(self, name, seconds, start=0.0, lowpass=None, xfade=2.0):
        """A sound as long as the reel, looped with a crossfade when it's shorter."""
        a = decode(self.find(name), lowpass)[int(start * RATE):]
        n, x = int(seconds * RATE), int(xfade * RATE)
        out = a[:n].copy()
        ramp = np.linspace(0, 1, x)[:, None]
        while len(out) < n:
            out = np.concatenate([out[:-x], out[-x:] * (1 - ramp) + a[:x] * ramp, a[x:]])
        return out[:n]


def replay_file(url):
    target = unquote(parse_qs(urlparse(url).query)['replay'][0])
    u = urlparse(target)
    if u.path.startswith('/reel/'):
        return VIEWER / u.path.lstrip('/')
    _, _, run, _, checkpoint = u.path.strip('/').split('/')  # api/runs/<id>/replay/<checkpoint>
    seed = parse_qs(u.query).get('seed', ['0'])[0]
    return RUNS / run / 'replays' / f'{Path(checkpoint).stem}-{seed}.jsonl.gz'


def events(path):
    """Per tick: the light, where the followed blob is, and (kind, x, y) events."""
    lines = gzip.open(path, 'rt').read().splitlines()
    info = json.loads(lines[0])['info']
    nests = {n['colony']: (n['x'], n['y']) for n in info['nests']}
    ticks, energy, food, stores = [], {}, {}, {}
    for line in lines[1:]:
        f = json.loads(line)
        ev = []
        alive = [c for c in f['creatures'] if c['energy'] > 0]
        now = {x['id']: (x['x'], x['y']) for x in f['food']}
        # a bite is what the eye sees: food gone from beside a blob, picked up or eaten alike
        for x, y in (p for fid, p in food.items() if fid not in now):
            if alive and min((c['x'] - x) ** 2 + (c['y'] - y) ** 2 for c in alive) < 1.0:
                ev.append(('bite', x, y))
        food = now
        for c in f['creatures']:
            if energy.get(c['id'], 0) > 0 and c['energy'] <= 0:
                ev.append(('death', c['x'], c['y']))
            energy[c['id']] = c['energy']
        for s in f.get('stores', []):
            if s['jelly'] > stores.get(s['colony'], s['jelly']):
                ev.append(('unload', *nests[s['colony']]))
            stores[s['colony']] = s['jelly']
        first = f['creatures'][0]  # the viewer's follow camera is on the first creature
        ticks.append((f.get('light', 1.0), (first['x'], first['y']), ev))
    return ticks, info['width']


def timeline(reel):
    """One entry per video frame, worked out the way harness.js renders them; and the frame each section starts on."""
    clips = {c['name']: c for c in reel['clips']}
    grids = {g['name']: g for g in reel['grids']}
    frames, starts = [], []
    still = lambda section, label=False: dict(section=section, ticks=None, label=label)
    for section in reel['order']:
        starts.append(len(frames))
        if section in grids:
            frames += [still(section, i == 0) for i in range(grids[section]['frames'])]
            continue
        url, c = clips[section]['url'], clips[section]['clip']
        ticks, width = events(replay_file(url))
        labels = c.get('labels', [])
        follow = 'follow' in parse_qs(urlparse(url).query, keep_blank_values=True)
        toggles = [k['at'] for k in c.get('keys', []) if k.get('key') in ('f', 'F')]
        shown, t = None, 0.0
        for shot in c['shots']:
            t = max(t, shot['from'])
            for _ in range(int((shot['to'] - shot['from']) / shot['speed'] * FPS)):
                t0, t = t, t + shot['speed'] / FPS
                on = next((i for i, l in enumerate(labels) if l.get('from', 0) <= t < l.get('to', 1e9)), None)
                frames.append(dict(section=section, ticks=ticks, span=(int(t0 * TICK_HZ), int(t * TICK_HZ)),
                                   speed=shot['speed'], width=width, label=on is not None and on != shown,
                                   close=follow != (sum(k <= t for k in toggles) % 2 == 1)))
                shown = on
        frames += [still(section) for _ in range(round(c.get('hold', 0) * FPS))]
    return frames, starts


def place(track, clip, at, gain, pan=0.0, rate=1.0):
    if rate != 1.0:
        clip = clip[np.arange(0, len(clip) - 1, rate).astype(int)]
    i = int(at * RATE)
    n = max(0, min(len(clip), len(track) - i))
    track[i:i + n, 0] += clip[:n, 0] * gain * np.cos((pan + 1) * np.pi / 4) * 1.41
    track[i:i + n, 1] += clip[:n, 1] * gain * np.sin((pan + 1) * np.pi / 4) * 1.41


def level(name, a):
    on = np.abs(a).max(axis=1) > 1e-4
    rms = 20 * np.log10(np.sqrt((a[on] ** 2).mean()) + 1e-9) if on.any() else -99
    peak = 20 * np.log10(np.percentile(np.abs(a[on]), 99.9) + 1e-9) if on.any() else -99
    print(f'  {name:18} rms {rms:6.1f} dB   peaks {peak:6.1f} dB')


def mix(reel, edit, sounds):
    frames, starts = timeline(reel)
    seconds = len(frames) / FPS
    rng = random.Random(1)
    fx = np.zeros((int(seconds * RATE), 2), np.float32)
    play = lambda s, at, gain=0.0, pan=0.0, rate=(1, 1): place(
        fx, sounds.get(rng.choice(s['sounds']), s.get('lowpass')), max(0.0, at), db(s['db'] + gain), pan, rng.uniform(*rate))
    light = []
    for i, f in enumerate(frames):
        at = i / FPS
        if f['ticks'] is None:
            light.append(light[-1] if light else 1.0)
        else:
            a, b = f['span']
            b = min(b, len(f['ticks']) - 1)
            lit, (cx, cy), _ = f['ticks'][b]
            light.append(lit)
            for tick in range(a + 1, b + 1):
                for kind, x, y in f['ticks'][tick][2]:
                    s = edit['world'].get(kind)
                    # sped up, everything but a death is too quick to see
                    if not s or (f['speed'] > 2 and kind != 'death'):
                        continue
                    if f['speed'] > 1 and rng.random() > s.get('fast', 1):  # fast: share kept when sped up
                        continue
                    if f['close']:
                        if (x - cx) ** 2 + (y - cy) ** 2 > CLOSE ** 2:
                            continue
                        play(s, at, 0, (x - cx) / 4, s.get('rate', (1, 1)))
                    else:
                        play(s, at, -4, x / (f['width'] / 2) * 0.6, s.get('rate', (1, 1)))
        if f['label'] and 'label' in edit:
            play(edit['label'], at - edit['label'].get('lead', 0))
    if 'cut' in edit:
        for start in starts[1:]:
            play(edit['cut'], start / FPS - edit['cut'].get('lead', 0.25))
    for where, s in edit.get('stings', {}).items():
        section, frame = where.split('@')
        play(s, (starts[reel['order'].index(section)] + int(frame)) / FPS)
    level('effects', fx)
    total = fx.copy()
    # from the replay's light: 0 by day, 1 in the dark, eased so dusk and dawn fade
    lit = np.convolve(np.pad(np.asarray(light), 4, mode='edge'), np.ones(9) / 9, mode='valid')
    lit = np.interp(np.arange(len(total)) / RATE, np.arange(len(lit)) / FPS, lit)[:, None]
    night = np.clip(1 - lit * 1.6, 0, 1)
    for amb in edit.get('ambience', []):
        when = {'night': night, 'day': 1 - night}.get(amb['when'], np.ones_like(night))
        bed = sounds.bed(amb['sound'], seconds, amb.get('start', 0), amb.get('lowpass')) * when * db(amb['db'])
        level(f"ambience ({amb['when']})", bed)
        total += bed
    m = edit['music']
    music = sounds.bed(m['track'], seconds, m.get('start', 0)) * (1 - night * m.get('night_dip', 0)) * db(m['db'])
    level('music', music)
    total += music
    fade = np.minimum(1, np.minimum(np.arange(len(total)), len(total) - np.arange(len(total))) / (RATE * 1.5))[:, None]
    return (total * fade).astype(np.float32)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('reel')
    p.add_argument('out')
    p.add_argument('profile')
    p.add_argument('--sounds', required=True, help='folder holding the sound files')
    args = p.parse_args()
    reel = json.loads(Path(args.reel).read_text())
    edit = json.loads((Path(__file__).parent / 'sound.json').read_text())[args.profile]
    out = Path(args.out)
    raw, wav = out / f'{args.profile}.f32', out / f'{args.profile}.wav'
    raw.write_bytes(mix(reel, edit, Sounds(args.sounds)).tobytes())
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'f32le', '-ac', '2', '-ar', str(RATE), '-i', str(raw),
                    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', str(RATE), str(wav)], check=True)
    raw.unlink()
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(out / reel['out']), '-i', str(wav), '-map', '0:v',
                    '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart',
                    str(out / f'{args.profile}.mp4')], check=True)
    print(out / f'{args.profile}.mp4')


if __name__ == '__main__':
    main()
