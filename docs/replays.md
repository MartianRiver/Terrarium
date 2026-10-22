# Replays

A replay is one arena's run, written by the sim and played by the viewer. Every viewer has to play every replay ever recorded (see [releasing.md](releasing.md)), so this format moves carefully.

## The file

Gzipped JSON lines, `.jsonl.gz`. The viewer also reads it unzipped.

Line 1 is the header:

```json
{"format": "terrarium-replay", "version": 1,
 "info": {"width": 26.0, "height": 26.0, "tickHz": 20, "maxSpeed": 2.4, "nests": [{"colony": 0, "x": 0.0, "y": 8.84, "radius": 1.6}]},
 "source": {"commit": "b969418", "seed": 0, "brain": "random", "arena": 0, "config": {}}}
```

Every line after it is one `Frame`, one per tick, starting from the tick before the first step. `info` and `Frame` are the types in [viewer/src/world.ts](../viewer/src/world.ts). `source` says where the run came from (commit, with `-dirty` if the working tree had changes; seed; brain; the full config). The viewer logs it and never depends on it.

Positions are in metres and angles in radians, rounded to 3 decimals. A creature's `size` is its radius over 0.45 m, the radius the blob model is drawn at. Food gets a new id every time it regrows, because the viewer pops things in and out by id.

## Changing it

- New fields can be added without bumping the version. The viewer ignores fields it doesn't know, so new ones have to be optional when read.
- Anything else (renaming, removing, changing what a field means) bumps `version`. The viewer keeps reading every older version, and turns down a newer one with a message saying so.
- Each released version leaves a sample in `samples/`, named after the release. The viewer's tests load every sample in there, so an old format can't quietly stop working.

## Recording

From `sim/`:

```
uv run python -m terrarium.record ../samples/0.1-random.jsonl.gz --seconds 30 --seed 0
```

That runs one arena with random actions. A 30 second replay is about 165 kB. It stops early if the episode ends: everyone dead, or `[episode] seconds` up. `--config configs/solo.toml` records the solo forager on its own.

To watch one, use **Open replay** in the viewer or drop the file anywhere on the page. It loops at the end; R restarts it.
