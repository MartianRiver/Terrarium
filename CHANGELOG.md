# Changelog

## Unreleased: 0.3 Daisy, colony basics

Kept as we go: each branch adds what it changed before it's merged, and the release turns this into the 0.3.0 entry.

Terrikins now live in a garden under a glass dome on Mars: a clay body with feet and a waddle, a face, a colony-coloured tail, droppings (drawn only), a follow camera (F) and a flyby into the dome (`&intro`). The public site at terrarium.martianriver.com plays the latest brain (`npm run site`). The tools that made the first Instagram reel are in `viewer/reel/`. Droppings are smaller now. `viewer/reel/0.3.json` is the second reel's script, and `viewer/reel/sound.py` gives a reel sound that matches what's on screen (bites, unloads, deaths, day and night ambience, music).

Training got faster and accounted for. torch has CPU and CUDA extras on Linux, `--device` and `--workers` split episodes over processes, and `terrarium.remote` trains on a rented GPU from a committed checkout. `terrarium.compute` adds up the hours of every run and the dollars of every rented machine (`sim/compute.toml`), and a promoted brain records what it took. The runs page (`runs.html`, with `terrarium.serve`) lists every run with its curves, live while it trains, and each checkpoint as a generation to watch.

The brain sees more (schema v2): the distance and direction to its own nest, whether a creature it sees is a nestmate, and how far its own and other nests are along each ray. The 0.2 brain loads and acts the same.

Colonies carry food home (schema v3). Food eaten past full goes into a crop, like an ant's social stomach, and slows the carrier down. Two new actions: unload, which puts the crop into the nest's store, or onto the ground as jelly anyone can eat, and eat, from the crop or (when hungry, at home) from the store. Two new inputs say how full the crop is and whether it's home. Food grows in patches that move each episode. The reward pays for storing, can be partly shared with the colony, and pays a little for carrying food closer to home (and takes it back for walking off), which only moves reward earlier. `carrier` is the new scripted baseline: greedy that takes a full crop home. A new yes/no action now starts out mostly no, so it's tried now and then; zero-padding it made it fire half the time in training, which is why nothing stored for the first eight runs (`docs/notes/0.3.md` has the whole story).

A dead Terrikin's body now leaves the world: nothing bumps into it or sees it. The viewer puts a small tombstone where it fell, which fades after 20 s. The replay clock runs on into hours and days.

The viewer can follow training: `/?latest` plays the newest checkpoint of each live run in turn (or `/?latest=text`, of the newest run with that in its name) and looks for a newer one each time the replay ends.

Evals v2: errors are taken over arenas rather than creatures, each number has a p10, and colonies get jelly eaten, deaths with jelly in their own store, colonies lost, and how often `unload` and `eat` say yes where they matter. A brain's `unload` and `eat` are drawn at the odds it gives them, in evals and replays, while it steers by its mean; `--modes mean` and `--modes sampled` score it all by the mean or all drawn as in training, and training ends by scoring it all three ways. `--held-out` plays the worlds kept for promotion.

Running out of time in training is no longer counted as an end: with `[ppo] bootstrap`, a creature cut off alive at the time limit is paid what its value says the rest is worth. Train configs can now hold true/false settings.

Brain schema v4: a Terrikin senses how much jelly its colony has, and how light it is. Older brains load with no weight on either and act as before. A train config's `[start] fresh` starts named actions of the parent brain over, as new actions start.

Nights, off unless a world turns them on (`[night]`): at nightfall the food standing goes and none grows back until dawn, the light fades at dusk and comes back after dawn, and the dark is cold, draining energy faster except in the nest or close to nestmates. Replays of worlds with nights carry the light. Evals count the nights each creature lives through, deaths in the dark and colonies still going at the first dawn, and `nester` joins the scripted baselines: carrier that heads home at dusk and waits out the night in the nest. A train config's `[start] staggered` starts each training arena at a random time of day, so a batch isn't all day or all night; evals still start at dawn.

A choice can be held for several ticks (`[ppo] repeat`): rewards over those ticks are summed, `gamma` and `lam` then count choices rather than ticks, and a brain trained that way acts that way in evals and replays. `[ppo] anneal = false` keeps the learning rate constant, for training in chunks. Two new rewards pay for warmth (`snug` at any time, `warm` in the dark), `train --no-evals` skips the end evals, and `train --mix WORLD:ARENAS` trains in arenas of other worlds beside the main one (solo ones, so a colony brain keeps foraging alone). Evals cap torch's threads on rented machines like training does.

The runs page shows the compute behind each brain: hours and dollars per machine for its run and every run behind its parent, back to the first, plus all training so far per machine, rented machines that never ran anything included. A rented machine's bill is split across the runs it hosted. Run records now keep the CPU, memory and the parent checkpoint's own notes (which run and how far in).

Training runs can go through a job queue (`docs/compute.md`): I sign each job, a coordinator hands jobs out, and workers on my machines, rented GPUs and later lent ones check the signature and every input, train, and send the run back. Donated machines only run code that's public on `main` or `next`. Rented machines have their own kind of token, and a batch can say `on = "rented"` to keep its jobs off my own machines (or `"trusted"` to keep them on).

The repo has a README, the MIT licence, and issue templates for bugs and ideas (issues are welcome; pull requests aren't taken).

Notes on what was tried in each stage, dead ends included, are in `docs/notes/`.

## 0.2.0: Solo forager

The first trained brain. One creature alone in the arena with 8 berries learns to keep itself fed. On the evals it eats 18.4 berries a minute and lives out every 3-minute episode. Random actions manage 0.26 and starve in under a minute. A scripted forager that beelines for the nearest berry it sees gets 13.8, so the brain beats that too.

The sim gained what a brain needs. Each creature casts 16 rays over 200°, out to 8 m, and gets back a distance and what was hit: wall, creature, food or block. Running out of energy now kills, though the body stays where it fell. Episodes end when everyone is dead or 3 minutes are up, and each arena restarts on its own. `configs/solo.toml` is the one-creature world. Rays are the expensive part: at 64 arenas with three colonies they cost 14× the physics (`docs/benchmark.md`). Solo, they cost about the same as the physics.

The brain is a small transformer, about 70k parameters, that attends over its own state plus one token per ray, with a type for each thing it can see. Later stages add types and inputs instead of reshaping it. What it sees and outputs is an append-only schema (`sim/terrarium/schema.py`). A saved brain has to match the start of today's lists, and loading one that doesn't fails with the place they part. Newer inputs load zeroed, so an older brain keeps working (`docs/brain.md`).

Training is PPO, with episodes played on the CPU and learning on the Mac's GPU. Every run gets a folder under `runs/` (outside git) with its commit, both configs, parent, schema, machine, versions, per-update metrics, checkpoints and final evals. Uncommitted code only trains as a scratch run. `terrarium.promote` takes a finished run from committed code on `next` that clearly beats random, backs the weights up outside the repo, and adds them to `sim/brains.toml`, the lineage. The 0.2 brain is `17cc35ad7932` there, and its weights are attached to this release (`docs/training.md`).

Evals v1 (`docs/evals.md`) score any policy on 64 fixed-seed episodes no run trains on: food per minute and seconds alive. "Clearly beats" means twice random's food and both numbers ahead by over three standard errors. `terrarium.record --brain` writes a replay of a brain. `samples/0.2-forager.jsonl.gz` is this version's sample, a full episode of the promoted brain.

torch is a new dependency: the CPU build on Linux, so CI doesn't download CUDA.

## 0.1.0: Sim core and replays

The real sim, headless in Python. Three colonies of six creatures on a 26 m arena with walls, nests, 28 berries that regrow somewhere new after they're eaten, and two blocks heavy enough that pushing one takes effort. Creatures steer with thrust and turn, collide and shove through pymunk, and burn energy as they go, though running out does nothing yet. For now their actions are random. Every balance number is in `sim/configs/world.toml`, and the loader refuses anything missing, unknown or the wrong type.

Physics was picked by measuring. A vectorised numpy sim and pymunk ran the same scene. pymunk was six times faster at 64 arenas and brings the static friction and joints later stages need. The cost is a few cm of overlap between bodies, which doesn't show in the viewer (`docs/physics.md`). The speed baseline is 1,432 ticks a second for 64 arenas on the M3 (`docs/benchmark.md`).

Runs are saved as replays: gzipped JSON lines, a header then one frame per tick, format v1 (`docs/replays.md`). The viewer opens them with a button or by dropping the file in, and loops them. The scripted demo is still what the viewer opens on. `samples/0.1-random.jsonl.gz` is this version's sample, and every later viewer has to play it.

CI runs the sim's tests and the viewer's tests, and has the sim write a replay that the viewer's loader then reads.

## 0.0.0: Visual demo

A 3D viewer for the world, with a scripted stand-in for the sim. Three colonies of six blobs hop around their nests, eat berries, shove two blocks around and flash signal colours. They squash and stretch, blink, look into their turns, and dim as their energy runs down. The viewer draws whatever sends it frames in the format in `viewer/src/world.ts`, which is what the sim's replays will use from 0.1.
