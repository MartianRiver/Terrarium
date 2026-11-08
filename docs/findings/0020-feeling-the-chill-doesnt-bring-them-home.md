# 0020 Feeling the chill doesn't bring the night brains home

date: 2026-11-08 · status: held-out · seeds: 2,000,000 × 256 · brains: n48-chill-s1, -s1b, -s2, -s2b (last checkpoints, 8.0M samples each on n43-nm-s1 and -s2); controls n45-nm3-s1, -s1b, -s2, -s2b

**Question.** The night brains walk out into the dark and die there (0017 to 0019). They can see the light fade, but nothing tells them how cold they are. Do they come home before dark once they can feel it: a `chill` input that builds up while they're out in the cold and fades in the nest or a huddle?

**World and brains.** The night world of 0014 to 0019 (one colony of two, the apple tree with burrow, a 60 s night in each 120 s cycle, dusk 10 s, drain 0.0125 a second, cold 0.005, 128 note slots), on schema v20 with `[night] chill_time` 20 s, `start_dark` 0. n48-chill is 8M samples from n43-nm-s1 and -s2 on 0.4's recipe with `[reward] needs` 1.0, two runs a parent; the one change is the chill input, which older brains load with zero weights. The control is n45-nm3, the same parents and 8M of the same recipe on v19, two runs a parent.

**Method.** `mates.py` on 256 games from seed 2,000,000, the same games for every brain, at 300 s (two nights) and 180 s (one night). Alive is the share of nims alive at the end, notes wiped for both nestmates whenever either stores (the "both" row). The controls were scored again beside n48 on the same code (next 632c593) and came out exactly as in 0019.

**Result.** Alive at the end, both row, each brain against the control from the same parent:

| parent | n45-nm3 (control) 300 s / 180 s | n48-chill 300 s / 180 s |
|---|---|---|
| n43-nm-s1 | s1 36 / 49, s1b 39 / 53 | s1 37 / 52, s1b 33 / 53 |
| n43-nm-s2 | s2 51 / 69, s2b 43 / 56 | s2 43 / 67, s2b 44 / 63 |
| mean | 42.3 / 56.8 | 39.3 / 58.8 |

**What it rules out.** That not knowing how cold they are is what keeps them out: with the chill to feel, the share alive moves by −8 to +7 points a brain, inside the spread between twins, and the mean doesn't rise. A likely reason, read from the code rather than tested here: `needs` pays only on eating, by the fall in hunger squared, so energy lost to the cold costs nothing in reward short of death, and a hungrier nim earns more from its next meal at home. Feeling a cost that the reward doesn't charge gives nothing to learn from. `[reward] needs_lost`, which charges energy as it's lost, is the next test.

**Limits.** Held-out seeds only, one block, 256 games a cell, two runs a parent. One `chill_time` (20 s). No battery run (0017's leave test), so whether the chill changed when they leave, as against how many live, wasn't measured.

**Replays and clips.** The channel's Nights line shows the question with its runs (backups `lab/channel/live/`).

**Links.** 0017 (they walk back out of the nest); 0018, 0019 (the forks that didn't help); 0014 (the needs reward); `../../ROADMAP.md`, 0.4.1.
