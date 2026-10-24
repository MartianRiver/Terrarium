# Reels

Each stage gets a short portrait video for Instagram, rendered from the viewer offline: a fake clock steps the page one frame at a time, so playback speed, timing and labels are exact and nothing depends on the window being visible. Tools are in `viewer/reel/`; a reel's whole script (every clip, its replay url and labels, text cards, grids and order) is one JSON file, e.g. `viewer/reel/0.2.json`.

## Rendering one

You need the viewer dev server (`npm run dev`), `terrarium.serve` (the replays come from the run's checkpoints, so the run named in the script's urls must be in `runs/`), ffmpeg, and Chrome.

1. `python3 reel/receive.py OUT` (from `viewer/`), with `OUT` somewhere outside the repo. It saves frames to `OUT/frames/<clip>/` and cards to `OUT/cards/`.
2. For each clip in the script, open the dev server's address + its `url` (e.g. `http://localhost:5173/?replay=…`), then in the console:
   `(await import('/reel/harness.js')).run('/reel/0.2.json', '<name>')`.
   `run` refuses a clip on the wrong url. Cards can be rendered from any page. A clip's `keys` can also turn the mouse wheel (`{at, zoom}`, + pulls back): in portrait the overview needs pulling back to fit the arena.
3. `python3 reel/build.py reel/0.2.json OUT` lays out the grids on a blurred backdrop, joins every section in `order` and encodes `OUT/<out>`.

Render the backdrop's source clip (`backdrop.from`) before building. Frames aren't byte-identical between renders (food spins and grass sway aren't seeded), but they match by eye.

## Instagram's limits (checked 2026-10-23)

- Meta's Reel specs: MP4 with the moov atom at the front, H.264, 4:2:0, 23–60 fps, at most 1920 px wide, 3 s to 15 min, 300 MB.
- Ads guide safe zone: keep text out of the top 14%, bottom 35% and 6% each side. Labels start at y 360 of 1920 and shrink to fit 86% of the width.
- Reels with borders or mostly text get recommended less, which is why grids sit on a blurred frame of the world and labels are short.
- The labels run at about 2.3 words a second, at least 3 s each. Faster than that was too quick to read while watching the footage.
