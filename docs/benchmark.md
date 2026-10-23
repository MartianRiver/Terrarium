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

The step alone is about 5% slower at one arena from the death bookkeeping; the rest of that drop is the per-tick reset check, which training pays too.

### With vision

The same, with every creature casting its rays each tick (16 rays over 200°, out to 8 m). This is the number from 0.2 on.

| when | what changed | 1 arena | 16 arenas | 64 arenas |
|---|---|---|---|---|
| 0.2, episodes-vision | rays in the sim | 3,804 | 407 (6,506) | 99 (6,327) |
| 0.2.0 release | nothing on the step path | 3,813 | 410 (6,555) | 103 (6,603) |

Vision is 14× the cost of everything else at 64 arenas, as [physics.md](physics.md) measured: every ray is tested against every other creature. It doesn't matter yet, since 0.2 trains one creature per arena (below), but it's the thing to speed up before 0.3 puts colonies back.

### Solo

`--config configs/solo.toml --arenas 1 64 256`: one creature per arena, what 0.2 trains on. Without vision, then with.

| when | what changed | 1 arena | 64 arenas | 256 arenas | 1 arena, vision | 64, vision | 256, vision |
|---|---|---|---|---|---|---|---|
| 0.2, episodes-vision | first solo numbers | 24,071 | 2,635 (168,648) | 690 (176,549) | 8,731 | 1,288 (82,416) | 351 (89,835) |
| 0.2, evals | solo food 28 → 8 (docs/evals.md) | 24,034 | 2,748 (175,867) | 719 (184,121) | 8,966 | 1,581 (101,154) | 444 (113,756) |
| 0.2.0 release | nothing on the step path | 24,144 | 2,829 (181,085) | 736 (188,528) | 8,846 | 1,600 (102,409) | 453 (115,854) |

Two runs in a row of the same code differed by up to 7% at 64 arenas (1,388 then 1,486), so a change smaller than that needs a few runs before it means anything.
