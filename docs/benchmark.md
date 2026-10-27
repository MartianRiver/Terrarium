# Benchmark

How fast the sim runs with random actions on `sim/configs/world.toml`, on the M3 MacBook, in one process. Each stage is held to this: a PR that makes it slower says why, and a release can't be slower than the last one without a written reason ([releasing.md](releasing.md)).

```
cd sim
uv run python bench/speed.py
```

It prints the commit it ran on and flags uncommitted changes. Run it with nothing else busy; other load moves the numbers.

Ticks a second for the whole batch, arena-ticks a second in brackets. Real time is 20 ticks a second, so one arena at 23,000 runs about 1,150× real time.

| when | what changed | 1 arena | 16 arenas | 64 arenas |
|---|---|---|---|---|
| 0.1, sim-world | first sim: 18 creatures, 28 food, 2 blocks, pymunk with 2 substeps | 23,280 | 4,998 (79,970) | 1,431 (91,587) |
| 0.1.0 release | replays added, nothing on the step path | 23,222 | 5,052 (80,833) | 1,432 (91,671) |
| 0.2, episodes-vision | death, episodes and resets; the bench checks for ended arenas every tick | 19,832 | 4,948 (79,162) | 1,433 (91,733) |
| 0.2.0 release | meal counts, nothing else on the step path | 20,475 | 5,032 (80,505) | 1,486 (95,093) |
| 0.3, jelly | crop, stores, unload and eat, dropped food, food patches, nights (off here) | 10,860 | 3,634 (58,145) | 1,150 (73,624) |
| 0.3.0 release | sprint, grab, smell, hatching, room to grow, flowers (all off here); on battery | 9,405 | 3,418 (54,688) | 1,106 (70,795) |

The step alone is about 5% slower at one arena from the death bookkeeping; the rest of that drop is the per-tick reset check, which training pays too.

### With vision

The same, with every creature casting its rays each tick (16 rays over 200°, out to 8 m). This is the number from 0.2 on.

| when | what changed | 1 arena | 16 arenas | 64 arenas |
|---|---|---|---|---|
| 0.2, episodes-vision | rays in the sim | 3,804 | 407 (6,506) | 99 (6,327) |
| 0.2.0 release | nothing on the step path | 3,813 | 410 (6,555) | 103 (6,603) |
| 0.3, colony-senses | rays also see nests and nestmates; circle tests keep x and y apart | 3,712 | 482 (7,715) | 118 (7,562) |
| 0.3, jelly | as above | 2,829 | 359 (5,751) | 86 (5,491) |
| 0.3.0 release | rays test for flowers too, even with none | 2,601 | 351 (5,618) | 86 (5,498) |

With vision, jelly's slowdown is food slots: an arena holds room for every crop to be dropped as jelly on the ground (28 growing plus 18 × 2), and the rays test all 64, present or not; with no crop (28 slots) vision takes 7.2 ms a tick at 64 arenas against 10.3. Testing only the food that's there would win that back. The step alone barely cares about slots (1.26 against 1.34 ms); its drop is the rest of jelly's bookkeeping. It's not urgent: training is about 90% PPO update. Nights cost nothing measurable (1.90 against 1.89 ms a step at 64 arenas with the night code stubbed out).

Vision is 14× the cost of everything else at 64 arenas, as [physics.md](physics.md) measured: every ray is tested against every other creature. It doesn't matter yet, since 0.2 trains one creature per arena (below), but it's the thing to speed up before 0.3 puts colonies back.

It still doesn't, with colonies: training 12 creatures per arena, the PPO update is about 90% of each round and collecting the samples (rays included) about 10%. So the speed-up so far is just the circle tests computing x and y apart instead of with `einsum`, about 45% faster each, which more than pays for seeing nests.

### Solo

`--config configs/solo.toml --arenas 1 64 256`: one creature per arena, what 0.2 trains on. Without vision, then with.

| when | what changed | 1 arena | 64 arenas | 256 arenas | 1 arena, vision | 64, vision | 256, vision |
|---|---|---|---|---|---|---|---|
| 0.2, episodes-vision | first solo numbers | 24,071 | 2,635 (168,648) | 690 (176,549) | 8,731 | 1,288 (82,416) | 351 (89,835) |
| 0.2, evals | solo food 28 → 8 (docs/evals.md) | 24,034 | 2,748 (175,867) | 719 (184,121) | 8,966 | 1,581 (101,154) | 444 (113,756) |
| 0.2.0 release | nothing on the step path | 24,144 | 2,829 (181,085) | 736 (188,528) | 8,846 | 1,600 (102,409) | 453 (115,854) |
| 0.3, colony-senses | rays also see nests and nestmates | 24,361 | 2,786 (178,289) | 734 (187,932) | 7,295 | 1,597 (102,233) | 468 (119,876) |
| 0.3.0 release | as above; on battery | 11,701 | 2,373 (151,866) | 668 (170,889) | 4,968 | 1,400 (89,601) | 434 (111,074) |

One arena with vision is about 18% slower from 0.3: seeing nests is more numpy calls a tick, a fixed cost that's gone by 64 arenas.

The 0.3.0 release is slower again where the cost per tick is fixed: one solo arena loses half its speed without vision and a third with it, 64 colony arenas 4%. Every feature 0.3 added to the step is checked each tick whether it's on or not, and the rays test for flowers on every tick even in worlds without any (a fourth set of circle tests). Nobody trains on one arena, and training is about 90% PPO update, so it's written down rather than fixed: skipping what's off is the fix if collecting ever matters. These were measured on battery, which may cost a little on its own.

Two runs in a row of the same code differed by up to 7% at 64 arenas (1,388 then 1,486), so a change smaller than that needs a few runs before it means anything.
