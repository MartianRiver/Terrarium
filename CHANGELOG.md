# Changelog

## 0.1.0: Sim core and replays

The real sim, headless in Python. Three colonies of six creatures on a 26 m arena with walls, nests, 28 berries that regrow somewhere new after they're eaten, and two blocks heavy enough that pushing one takes effort. Creatures steer with thrust and turn, collide and shove through pymunk, and burn energy as they go, though running out does nothing yet. For now their actions are random. Every balance number is in `sim/configs/world.toml`, and the loader refuses anything missing, unknown or the wrong type.

Physics was picked by measuring. A vectorised numpy sim and pymunk ran the same scene. pymunk was six times faster at 64 arenas and brings the static friction and joints later stages need. The cost is a few cm of overlap between bodies, which doesn't show in the viewer (`docs/physics.md`). The speed baseline is 1,432 ticks a second for 64 arenas on the M3 (`docs/benchmark.md`).

Runs are saved as replays: gzipped JSON lines, a header then one frame per tick, format v1 (`docs/replays.md`). The viewer opens them with a button or by dropping the file in, and loops them. The scripted demo is still what the viewer opens on. `samples/0.1-random.jsonl.gz` is this version's sample, and every later viewer has to play it.

CI runs the sim's tests and the viewer's tests, and has the sim write a replay that the viewer's loader then reads.

## 0.0.0: Visual demo

A 3D viewer for the world, with a scripted stand-in for the sim. Three colonies of six blobs hop around their nests, eat berries, shove two blocks around and flash signal colours. They squash and stretch, blink, look into their turns, and dim as their energy runs down. The viewer draws whatever sends it frames in the format in `viewer/src/world.ts`, which is what the sim's replays will use from 0.1.
