# Physics: pymunk

The sim uses [pymunk](https://www.pymunk.org) (Chipmunk2D) for bodies and contacts, with ray vision written in numpy on top. Decided in 0.1 by running both options on the same scene; the code is in `sim/bench/` and reruns with:

```
cd sim
uv run python bench/physics_choice.py
```

## The test

The stage 0 demo's arena: 26 m square, 18 creatures (0.45 m circles, 2.4 m/s), 30 food, a light 1.3 m block (4 kg) and a heavy 2.4 × 1.1 m slab (12 kg), at 20 ticks a second. Both candidates get the same random actions, the same steering, the same food logic and the same ground friction on blocks (1.2 m/s² sliding, with a matching spin friction), so the only difference is how contacts are solved.

- **numpy:** every arena in one set of arrays. Position-based: move everything, push overlaps apart (3 passes), read velocity back off how far things moved. Circle vs box, box corners vs box faces and walls.
- **pymunk:** one Space per arena, body state in and out through `pymunk.batch`. Creatures are pushed by a force each tick (setting velocity directly undoes the solver's contact pushes, and creatures sank 20 cm into each other). Block friction is a pivot and gear joint to the ground with a force limit, so a block doesn't move until it's pushed harder than its friction. 2 substeps a tick, 1 cm slop.

Both run the same every time from the same seed.

## Results

M3, Python 3.13.7, numpy 2.5.4, pymunk 7.3.1, one process. Ticks a second for the whole batch, arena-ticks a second in brackets.

| | 1 arena | 16 arenas | 64 arenas |
|---|---|---|---|
| numpy physics | 1,393 | 732 (11,717) | 307 (19,667) |
| pymunk physics | 41,083 | 6,550 (104,801) | 1,815 (116,137) |
| numpy rays | 4,807 | 432 (6,906) | 105 (6,706) |
| pymunk rays | 1,795 | 111 (1,772) | 27 (1,714) |

Rays are 16 per creature over 200°, out to 8 m, hitting walls, creatures, food and blocks. numpy's rays and pymunk's own segment queries give the same answer on every ray (worst gap under 1e-12 m), which also checks the numpy ray code.

Over 60 seconds in 16 arenas, both eat the same food (35 per arena), and the light block moves and turns the same amount. The difference is overlap, worst across all 16 arenas each tick:

| | creature/creature worst / mean | creature/block worst / mean |
|---|---|---|
| numpy | 1.5 cm / 0.04 cm | 0.1 cm / 0.00 cm |
| pymunk, 1 substep | 16 cm / 3.2 cm | 11 cm / 1.4 cm |
| pymunk, 2 substeps | 7.8 cm / 1.7 cm | 5.3 cm / 0.9 cm |
| pymunk, 4 substeps | 3.7 cm / 1.1 cm | 2.3 cm / 0.6 cm |

Each doubling of substeps costs about a third of the speed (64 arenas: 2,654 → 1,898 → 1,210 ticks a second).

## Why pymunk

- Physics is 6× faster at 64 arenas and 30× faster at one. The numpy version isn't limited by any one part that could be fixed: at one arena it's the fixed cost of a few hundred small numpy calls a tick, and at 64 the pairwise creature pass is most of it. Tightening that might double it, which still leaves it well behind.
- It's real rigid-body physics. Static friction thresholds, mass and joints come with it, and the later stages need exactly those: a heavy block that one creature can't shift but two can (0.5), two creatures holding rich food (0.4). In the numpy version every push eventually moves anything, and joints would have to be written from scratch.
- The cost is softer contacts: a couple of cm of overlap normally, up to about 8 cm in a pile-up, on a 45 cm body. That isn't visible in the viewer. If it matters, 4 substeps halves the worst case.

## What it means later

- **Vision is the expensive part, not physics.** At 64 arenas the rays take about 17× as long as the physics. That's where 0.2 should spend effort: float32, skipping things out of range, or casting on the GPU alongside the brain.
- Ray casting stays in numpy rather than pymunk's queries, which are 4× slower because each ray is a Python call.
- Arenas are independent Spaces, so they split across processes when one core isn't enough. Not measured yet.
- Not tried: a compiled custom engine (numba, JAX) or running thousands of arenas on a GPU. Worth a look only if training ends up waiting on the sim.
