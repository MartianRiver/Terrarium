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

No vision or brain yet; from 0.2 those come into the number, and rays alone cost more than all of this ([physics.md](physics.md)).
