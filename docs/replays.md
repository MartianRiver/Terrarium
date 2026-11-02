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

From 0.3 each creature has `carrying` (food in its crop) and each frame has `stores`, a list of `{colony, jelly}` with the food in each colony's store. Replays from before have neither; the viewer reads them as 0 and empty. Worlds with nights also give each frame `light`, from 1 by day to 0 at night; without it, it's always day. In worlds with grab on, each creature has `holding`, 1 while it grips a block (drawn as an arm reaching to it).

A dead creature stays in the frames with `energy` 0 where it fell, and the viewer draws a tombstone there that fades after 20 s. From 0.3 the sim takes a dead body out of the world (nothing bumps into it or sees it); in older replays it could still be pushed, and its stone stays where it died.

Positions are in metres and angles in radians, rounded to 3 decimals. A creature's `size` is its radius over 0.45 m, the radius the blob model is drawn at. Food gets a new id every time it regrows, and a hatchling gets a new one too, because the viewer pops things in and out by id.

Worlds with hatching give each frame `eggs`, a list of `{id, colony, x, y, progress}`: an egg lies where its Terrikin will hatch, `progress` goes from 0 when it's laid to 1, and the hatchling takes the egg's id, so the viewer cracks the egg and grows the hatchling from small to full size in its place. A colony's places it hasn't hatched into yet (`[colonies] room`) aren't in the frames at all.

Worlds with sprint give each creature `sprinting`, 1 mid-burst (drawn with dust kicked up behind it). Worlds with nectar flowers give each frame `flowers`, a list of `{id, x, y}` of the ones open, and each creature `nectar`, the seconds left of its boost (drawn with a happy face, and an antenna and jelly belly shimmering through a lorikeet's colours). A flower that leaves the list was drunk or closed, and the viewer folds it shut. Worlds with carry give each creature `load`, 1 while it has a berry in its jaws (drawn on top of its head); the berry itself leaves `food` while it's carried and comes back where it's put down. Worlds with `[young]` give each creature `young`, the share of its childhood left (drawn as a baby, the size of its body like everyone else). Worlds with `[tired]` give each creature `stamina`, 0 to 1 (drawn with heavy lids, a slower slumped waddle and a drooping antenna when it's low, and little z's floating up while it rests); without it the viewer reads 1. The nursery games reuse what's there: in tag the one who's it has its bulb lit yellow (signal 0); in hide-and-seek seekers show pink (signal 2) while they wait for the hiders; in capture the flag each frame has `flags`, `{colony, x, y, down, carrier}` for each colony's flag (where it is, 1 when it's lying where it was put down, and its carrier's id or -1), drawn as a pennant in its colony's tint on its nest, on the grass or on its carrier's back (replays from before had a carrier's `load` 1 instead, drawn as a berry on its head); in peekaboo the berry gets `hidden: 1` once it's out of the Terrikins' sight (drawn faint). Worlds with `[dung]` give each frame `dung`, a list of `{id, x, y}` of the droppings lying on the ground, and with carry each creature `dung`, 1 while it carries one (drawn as a pellet on its head); the header's info has `midden`, how far past the nest's edge a dropping has to go in the tidy nursery, drawn as a dashed ring (absent or 0 elsewhere), or, where the midden is a spot (`[dung] spot`), `middenSpot`, `{x, y, radius}` for that episode's spot, drawn as a dashed ring round it, with `midden` left out so a viewer from before draws no line. Worlds with `[jump]` give each creature `z`, how high it is off the ground in metres (the viewer lifts it that far). In the tree nursery the header's info has `tree`, the id of the block that is the trunk (drawn as an apple tree in place of a block), and its food has `kind: "apple"` and `z`, how far above a standing Terrikin's reach it hangs (drawn hanging there on a branch from the trunk). Without `frame.dung` the viewer goes on drawing pretend droppings after meals, as it always has. Older replays have none of these; the viewer reads them as 0 and empty. `&preview` lays make-believe flowers and sprints over any replay, to see the look without them.

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

To watch one, use **Open replay** in the viewer or drop the file anywhere on the page. It loops at the end; R restarts it. F follows the creature from close up (the first one, while there are colonies), and `&follow` in the address does the same from the start. `&nodroppings` hides the droppings (viewer-only, after every third meal). `&intro` starts low outside the dome, circling slowly until the first F swoops down to the creature. `&lite` draws for a laptop on battery: one pixel per point, no antialiasing, shadows or bloom, and at most 30 frames a second.
