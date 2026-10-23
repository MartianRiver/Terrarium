# Builds a reel from rendered frames: the grids (cells on a blurred backdrop, under a text card), then every
# section in order, encoded for Instagram (H.264, yuv420p limited range, closed 1 s GOPs, faststart).
# python3 reel/build.py reel/0.2.json OUT
import json
import subprocess
import sys
from pathlib import Path

reel = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
frames = out / 'frames'


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *args], check=True)


# a blurred frame of the world, not a plain colour: Instagram recommends reels with borders less
def backdrop():
    b = reel['backdrop']
    path = out / 'backdrop.jpg'
    ffmpeg('-i', str(frames / b['from'] / f"{b['frame']:05d}.jpg"), '-vf', 'boxblur=24:3,eq=brightness=-0.06', '-q:v', '2', str(path))
    return path


def grid(g, back):
    w, h = g['cell']
    cells, cols = g['cells'], g['cols']
    args, f = [], ''
    for i, c in enumerate(cells):
        args += ['-framerate', '30', '-i', str(frames / c / '%05d.jpg')]
        f += f'[{i}]scale={w - 6}:{h - 6},pad={w}:{h}:3:3:color=0x2f4724[c{i}];'
    n = len(cells)
    layout = '|'.join(f'{i % cols * w}_{i // cols * h}' for i in range(n))
    f += ''.join(f'[c{i}]' for i in range(n)) + f'xstack=inputs={n}:layout={layout}[g];'
    f += f"[{n + 1}][g]overlay=0:{g['top']}:shortest=1[b];[b][{n}]overlay=0:0"
    dest = frames / g['name']
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob('*.jpg'):
        old.unlink()
    ffmpeg(*args, '-loop', '1', '-i', str(out / 'cards' / f"{g['card']}.png"), '-loop', '1', '-framerate', '30', '-i', str(back),
           '-filter_complex', f, '-frames:v', str(g['frames']), '-q:v', '2', str(dest / '%05d.jpg'))


def join():
    joined = out / 'joined'
    joined.mkdir(exist_ok=True)
    for old in joined.iterdir():
        old.unlink()
    n = 0
    for section in reel['order']:
        shots = sorted((frames / section).glob('*.jpg'))
        if not shots:
            sys.exit(f'no frames for {section}')
        print(section, len(shots))
        for shot in shots:
            (joined / f'{n:05d}.jpg').symlink_to(shot.resolve())
            n += 1
    return joined, n


back = backdrop()
for g in reel['grids']:
    grid(g, back)
joined, n = join()
video = out / reel['out']
ffmpeg('-framerate', '30', '-i', str(joined / '%05d.jpg'), '-vf', 'scale=in_range=full:out_range=limited,format=yuv420p',
       '-color_range', 'tv', '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-g', '30', '-flags', '+cgop',
       '-movflags', '+faststart', str(video))
print(f'{video}: {n} frames, {n / 30:.1f} s')
