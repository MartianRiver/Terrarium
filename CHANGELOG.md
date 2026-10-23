# Changelog

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
