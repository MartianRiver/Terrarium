# 0022 Charging them for the energy the cold takes doesn't bring the night brains home either

date: 2026-11-08 · status: confirmed · seeds: 2,000,000 × 256 (held-out), 8,115,000 × 256 (fresh) · brains: n49-lost-s1, -s1b, -s2, -s2b (last checkpoints, 8.0M samples each on n43-nm-s1 and -s2); controls n48-chill and n45-nm3 from the same parents

**Question.** 0020 found that feeling the chill doesn't bring them home, and read a likely reason from the code: `needs` pays only on eating, so energy lost to the cold costs nothing in reward short of dying. Does charging for it fix that: `[reward] needs_lost`, which takes off the energy each nim loses to the drain and the cold as it goes, on top of `needs`?

**World and brains.** The world of 0020 (the night world of 0014 to 0019 with the chill input, schema v20, `chill_time` 20 s). n49-lost is 8M samples from n43-nm-s1 and -s2 on n48's recipe with `[reward] needs_lost` 1.0 added, two runs a parent (next 024c28e); the one change from n48 is that reward term. Controls: n48-chill (chill, no needs_lost) and n45-nm3 (neither), the same parents.

**Method.** As 0020: `mates.py` on 256 games from seed 2,000,000, the same games for every brain, at 300 s (two nights) and 180 s (one night); alive is the share of nims alive at the end, the "both" row (notes wiped for both nestmates whenever either stores). Scored on the same code as 0020's (Terrarium-review 632c593), so the control numbers are 0020's.

**Result.** Alive at the end, both row, 300 s / 180 s:

| parent | n45-nm3 | n48-chill | n49-lost |
|---|---|---|---|
| n43-nm-s1 | s1 36 / 49, s1b 39 / 53 | s1 37 / 52, s1b 33 / 53 | s1 42 / 56, s1b 37 / 53 |
| n43-nm-s2 | s2 51 / 69, s2b 43 / 56 | s2 43 / 67, s2b 44 / 63 | s2 39 / 54, s2b 45 / 67 |
| mean | 42.3 / 56.8 | 39.3 / 58.8 | 40.8 / 57.5 |

"Both" is the harder row: both nestmates' notes are wiped whenever either stores an apple, not "both alive". With notes kept, n49 has 46 / 52 / 44 / 52 alive at 300 s (s1, s2, s1b, s2b; mean 48.5) and 66 / 70 / 64 / 70 at 180 s, against n45-nm3's 51.5 at 300 s kept: higher than the both row, and still flat.

On the fresh block 8,115,000, never used for choosing, the both row at 300 s / 180 s: n49-lost s1 38 / 53, s2 34 / 48, s1b 31 / 46, s2b 41 / 61 (mean 36.0 / 52.0); n45-nm3 s1 29 / 46, s2 45 / 64, s1b 31 / 45, s2b 38 / 50 (mean 35.8 / 51.3). Flat again.

**What it rules out.** That the missing cost of the cold is what keeps them out at night: with the energy it takes charged as it goes, the share alive moves by −4 to +5 points against n48 from the same parent and the mean stays between the two controls. With 0018 to 0020, four single changes (more of the same training, three pays, starting at nightfall with a dawn pay, the chill sense, and now this) leave the night where n45 had it.

**Limits.** 256 games a cell, two runs a parent; one weight for `needs_lost` (1.0, the same as `needs`). No battery run (0017's leave test), so when they leave wasn't measured, only how many live. Seed 2,000,000 has been used to choose between night brains all along; the fresh block above confirms the flat result, against n45 only (n48 wasn't rescored there). The intervals in the score logs are over deliveries, not over the share alive. The cold in every scoring world here, and in training, is 0.005 a second at full dark, a quarter of the colony world's 0.02; 0018's cold fork trained at 0.02, four times the test's cold, not "as cold as the test" as 0018 puts it.

**Replays and clips.** The channel's Nights line shows the question with its runs (backups `lab/channel/live/`).

**Links.** 0020 (the chill sense, and the reading this tests); 0017 (they walk back out of the nest); 0018, 0019; 0014 (the needs reward); `../../ROADMAP.md`, 0.4.1.
