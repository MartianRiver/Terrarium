# Reels

Each stage gets a short portrait video for Instagram, rendered from the viewer offline: a fake clock steps the page one frame at a time, so playback speed, timing and labels are exact and nothing depends on the window being visible. Tools are in `viewer/reel/`; a reel's whole script (every clip, its replay url and labels, text cards, grids and order) is one JSON file, e.g. `viewer/reel/0.2.json`.

Every reel opens outside the dome and swoops in to the blobs (`&intro` on the first clip's url, then an F key a few seconds in), like the start of a nature series episode.

## Rendering one

You need the viewer dev server (`npm run dev`), `terrarium.serve` (the replays come from the run's checkpoints, so the run named in the script's urls must be in `runs/`), ffmpeg, and Chrome.

1. `python3 reel/receive.py OUT` (from `viewer/`), with `OUT` somewhere outside the repo. It saves frames to `OUT/frames/<clip>/` and cards to `OUT/cards/`.
2. For each clip in the script, open the dev server's address + its `url` (e.g. `http://localhost:5173/?replay=…`), then in the console:
   `(await import('/reel/harness.js')).run('/reel/0.2.json', '<name>')`.
   `run` refuses a clip on the wrong url. Close-ups can follow one Terrikin (`&follow&pick=<id>`), hold on a spot (`&look=x,y,heading`), or be seen from another side (`&turn=<degrees>`, to catch a face coming towards the camera). In tag, `&cone=<degrees>` lays the it's view on the ground as a fan (200 for the nursery's rays), so what it can't see shows. Cards can be rendered from any page. A clip's `keys` can also turn the mouse wheel (`{at, zoom}`, + pulls back): in portrait the overview needs pulling back to fit the arena.
3. `python3 reel/build.py reel/0.2.json OUT` lays out the grids on a blurred backdrop, joins every section in `order` and encodes `OUT/<out>`.

A replay that isn't one of a run's checkpoints (one recorded with `terrarium.record` in another world, say) has to come from the dev server too, since the viewer won't fetch replays from another site: copy it to `reel/tmp-<name>.jsonl.gz` while rendering (git ignores `reel/tmp-*`). A replay where everyone dies ends on that tick, and the viewer starts it over, so a shot has to stop just before the end.

Render the backdrop's source clip (`backdrop.from`) before building. Frames aren't byte-identical between renders (food spins and grass sway aren't seeded), but they match by eye.

## Sound

`reel/sound.py` mixes a reel's sound onto `build.py`'s video, from the same script, so it lines up with every frame:

- World sounds come from the replays the clips were cut from: a bite when food vanishes beside a blob, an unload when a store grows, a death when energy reaches 0, a soft shell crack when an egg hatches, a sparkle when a Terrikin eats a nectar flower. Only what's on screen makes a sound: in a close-up, things within 3.5 m of what it follows (the blob `&pick` names, or the spot `&look` holds); from overhead, everything, a little quieter. Sped past 2×, only deaths.
- A sound when each label appears and just before each cut, the music under it all, and ambience by day and by night from the replay's light (crickets at night, birds by day).
- The levels are a profile in `reel/sound.json` (`garden` for the 0.3 reel): the music sets the mood, the effects stay soft (peaks a few dB under the music, low-passed), so it doesn't sound harsh.

Run it with the sim's Python (it needs numpy): `../sim/.venv/bin/python reel/sound.py reel/0.3.json OUT garden --sounds DIR`. It prints each layer's level, so the balance can be checked without listening. The sound files aren't in the repo: they're Kenney's CC0 packs, CC0 files from Freesound and the Free Music Archive, and Pixabay effects, whose licence doesn't allow passing them on as files. No Pixabay music: a track that showed no Content ID shield when it was downloaded got the 0.3 wrap-up drafts blocked on YouTube two days later, and reel 2 had used it. `garden-quiet` is the garden profile without music, and `garden-pluto` (the 0.3 wrap-up's) puts "A Small Town On Pluto" by HoliznaCC0 under it, a CC0 track from the Free Music Archive.

## Instagram's limits (checked 2026-10-23)

- Meta's Reel specs: MP4 with the moov atom at the front, H.264, 4:2:0, 23–60 fps, at most 1920 px wide, 3 s to 15 min, 300 MB.
- Ads guide safe zone: keep text out of the top 14%, bottom 35% and 6% each side. Labels start at y 360 of 1920 and shrink to fit 86% of the width.
- Reels with borders or mostly text get recommended less, which is why grids sit on a blurred frame of the world and labels are short.
- The labels run at about 2.3 words a second, at least 3 s each. Faster than that was too quick to read while watching the footage.
