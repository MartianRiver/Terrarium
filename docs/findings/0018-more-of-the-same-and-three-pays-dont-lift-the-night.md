# 0018 More of the needs pay, two-night games, pay for warmth and full cold: none lifts the night brains

date: 2026-11-08 · status: held-out · seeds: 2,000,000 × 256 · brains: n44-ep300-s1, -s1b, -s2, -s2b; n45-nm3-s1, -s1b, -s2, -s2b; n46-warm-s1, -s2; n46-cold-s1, -s1b, -s2, -s2b; controls n43-nm-s1, -s2 (last checkpoints, 8.0M samples each on their parents)

**Question.** The needs reward lifted the night brains and then stopped (0014). From the best of them, does any one more change get more nims through the night: games two nights long in training, a third 8M of the same, a little pay for being warm in the nest, or training in dark as cold as the test?

**World and brains.** The night world of 0014, 0015 and 0017: one colony of two, the apple tree with burrow, a 60 s night in each 120 s cycle, dusk 10 s, drain 0.0125 a second, 128 note slots. Every fork is 8M samples on 0.4's recipe with `[reward] needs` 1.0, one change each, two runs a parent where there are four (the `b` runs, different seeds). n44: from n41-needs-s1/s2 (n43-nm's parents) with 300 s training games instead of 180 s; its control is n43-nm, the same parents and 8M at 180 s. n45: from n43-nm-s1/s2, the same recipe again. n46-warm: from n43-nm with `snug` 0.003 and `warm` 0.1; n46-cold: from n43-nm with cold 0.02 in training (the test's dark); their control is n45, the same parents and recipe without the change.

**Method.** `mates.py` on 256 games from seed 2,000,000, the same games for every brain, at 300 s (two nights, the 0.4.1 gate's length: `nights44/world.toml`) and 180 s (one night: `nights43/world.toml`). Alive is the share of nims alive at the end, notes wiped for both nestmates whenever either stores (the "both" row).

**Result.** Alive at the end, both row, each run (mean in brackets):

| brains | change | 300 s | 180 s |
|---|---|---|---|
| n43-nm s1 / s2 | control for n44 and n45 | 42 / 50 (46) | 54 / 70 (62) |
| n44-ep300 s1 / s1b / s2 / s2b | 300 s training games | 26 / 36 / 45 / 48 (39) | 45 / 49 / 56 / 62 (53) |
| n45-nm3 s1 / s1b / s2 / s2b | a third 8M of the same | 36 / 39 / 51 / 43 (42) | 49 / 53 / 69 / 56 (57) |
| n46-warm s1 / s2 | pay for warmth in the nest | 38 / 25 (32) | 56 / 46 (51) |
| n46-cold s1 / s1b / s2 / s2b | the dark as cold as the test | 41 / 33 / 46 / 48 (42) | 59 / 53 / 70 / 62 (61) |

Two-night games are worse than one-night games at both lengths (39 against 46 at 300 s, 53 against 62 at 180 s). A third 8M is flat to down (42 against 46, 57 against 62). Pay for warmth is level on s1 (38 and 56 against n45-s1's 36 and 49) and 10 to 26 points down on s2 against n45's two s2 runs, the second time it has failed (the first was on brains that didn't eat yet). Full cold is level at 300 s (42 against n45's 42) and 4 points up at 180 s (61 against 57), inside the spread between twins. Twins from one parent differ by up to 10 points (n44 s1 26 and s1b 36), so a run alone can't show a change of 5.

**What it rules out.** That the night brains are short of training at this recipe: more of the same has stopped paying. That two-night games, a per-second pay for warmth, or a colder training dark gets them home: none lifts the share alive. Together with 0017 (they walk out of the nest fed and stocked), what's left to try changes what the nest means to a brain at night, not how much it trains or how warm the nest feels.

**Limits.** Held-out seeds only, one block, 256 games a cell. Two runs a cell for warm, four for the others, so the means carry a few points of noise. All from the n43-nm line and its parents: one family of brains. n44's control is n43-nm (same parents, same 8M at 180 s) and the others' is n45, as the batch notes set them; n46's controls are 8M further on than n44's.

**Replays and clips.** The channel's Nights line shows each of these questions with its runs (backups `lab/channel/live/`).

**Links.** 0014 (the needs reward lifts them, then stops); 0015 (they die out in the dark, not by deadlock); 0017 (they walk back out of the nest); `../../ROADMAP.md`, 0.4.1.
