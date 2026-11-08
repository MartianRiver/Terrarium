# 0014 The needs reward is the one change that lifts the night brains; gamma .998 on top costs, and none gets near 85%

date: 2026-11-07 · status: held-out · seeds: 2,000,000 × 256 games (scores), 8,108,000 × 256 (battery) · brains: n41-{st,g998,needs}-s1..3, n42-gn-s1..3, n43-nm and n43-ng s1, s2, n42-fresh-s1; matched control nightq3-s1..3

**Question.** From the nightq brains, which single change lifts the share alive through the night: staggered starts, gamma 0.998, or the needs reward, and does more of the winner, or a second change on top, add anything?

**World and brains.** The night world of 0012 (`nightq/world.toml`): one colony of two, the apple tree with burrow, a 60 s night in a 120 s cycle (dusk 10 s), cold 0.005, drain 0.0125 a second, 180 s games, 128 note slots. The parents are nightq2-s1..3 (8.0M samples in this world). Every fork is 8M more samples from the parent's last checkpoint on the nightq2 recipe, changing one thing; the control is nightq3, the parents plus 8M on the unchanged recipe. n41: `st` is `[start] staggered = true`; `g998` is gamma 0.99 → 0.998; `needs` is `[reward] needs` 0 → 1.0 (pays meals eaten from the store). n42-gn: needs 1.0 on each n41-g998 brain. n43-nm: another 8M of the n41-needs recipe on n41-needs-s1 and s2; n43-ng: 8M on them with gamma 0.998 (the s3 line left out, it never lives). The n43 world is the n41 one plus `[home] compass = true`, a key the strict loader now wants, set as the old worlds always played. n42-fresh-s1 is the probe: a fresh brain with memory, no parent, 8M of the n42 recipe (needs, gamma 0.998) in the same world.

**Method.** `mates.py` on 256 games from seed 2,000,000, the same games for every brain, notes wiped on unloading for both nestmates whenever either stores (its "both" row, the standard condition) and, in brackets, kept. Alive is the share of nims alive at 180 s. No interval was computed between brains. Then the frozen night battery of 0012 (seed 8,108,000 × 256, notes kept, conditions A to E) on n41-needs-s1, n41-needs-s2 and n42-gn-s2. The batch files, score logs and battery output are in the lab folder, outside the repo.

**Result.** Alive at 180 s, both row (kept row in brackets), and the change against the matched control nightq3 in the "both" row:

| | s1 | s2 | s3 | change vs control (s1 / s2 / s3) |
|---|---|---|---|---|
| control nightq3 (8M, no change) | 27 (23) | 45 (59) | 5 (3) | |
| st, staggered starts | 35 (41) | 44 (46) | 0 (1) | +8 / -1 / -5 |
| g998, gamma 0.998 | 31 (28) | 53 (67) | 19 (18) | +4 / +8 / +14 |
| needs 1.0 | 43 (54) | 66 (71) | 4 (1) | **+16 / +21 / -1** |
| gn, needs on g998 | 22 (26) | 54 (73) | 6 (17) | -5 / +9 / +1 (vs g998: -9 / +1 / -13) |
| nm, +8M of needs | 54 (65) | 70 (76) | | vs needs: +11 / +4 |
| ng, gamma 0.998 on needs, +8M | 44 (64) | 47 (71) | | vs nm: -10 / -23 |
| fresh brain, 8M | 0 (0) | | | |

Needs gave the biggest lift on s1 and s2 and none on s3, whose line never lives (4% with needs, 5% control; 19% at best, with gamma 0.998). Apples a minute to the nest, both row: needs 3.98 / 5.01 / 2.57 against control 3.06 / 4.29 / 2.31. Staggered starts move the three seeds by +8, -1 and -5 (kept row +18, -13, -2): no direction, and the best view we have of how far one trained brain wanders with no clear cause. Gamma 0.998 is up on all three seeds, by 4 to 14. Needs on top of g998 is worse than g998 on s1 and s3 (-9, -13) and flat on s2. Another 8M of needs adds 11 points on s1 and 4 on s2 (kept 11 and 5): a rise, smaller on the second seed, and a plateau near 70% for the better line. Gamma 0.998 on needs costs 10 and 23 points against the same 8M without it (kept row -1 and -5, so most of the loss is when the notes are wiped). The gap between kept and wiped, in points on s2: control 14, needs 5, nm 6, g998 14, gn 19, ng 24; the gamma 0.998 brains lean on their notes most. The fresh brain has 0% alive and no apples brought home at 8M.

The battery (notes kept, seed 8,108,000, alive in control 46 / 70 / 66% for needs-s1, needs-s2, gn-s2): 86–98% of the deaths are in the dark, a median 7.0–8.0 m from the nest's middle, with an empty crop in 97–99%, and **the store is empty at death in 51–60%** (0012's three brains died with jelly at home in 70–96%). Holding the light at day (E) leaves 20 / 1 / 2% alive. A hungry start in a stocked nest (A) is +6 / +10 / +17 points and 1.5 m outside it (B) -3 / +10 / +12; 7 m out and lean by day (C) is -17 / -47 / -38; an apple at dusk (D) is +2 / +1 / +5.

**What it rules out.** That staggered starts lift the night brains alone: the change has no direction. That gamma 0.998 is worth adding to the needs brains: it cost on both seeds. That a fresh brain skips the earlier rungs at this budget: 0% in 8M, one seed. That the two-night gate is close: the best line is 54 and 70% wiped at 180 s, and 0015 puts the same brains at 40 to 50% over 300 s. The store running dry before about half the deaths, with the light still the cue to go home, says the brains' trouble has moved from having jelly at home to the length of the night (0015).

**Limits.** All at 180 s, which holds one night; the 0.4.1 gate counts 300 s, two nights (set on 7 Nov), where the same brains score lower (0015). One trained brain a cell: no repeats, so a change of a few points on one seed is not a result, and the staggered row is the only gauge of that noise. No interval between brains; at 256 games a cell's share carries a standard error of 2 to 3 points, more with the two nims of a game paired. Seed block 2,000,000 was used to pick which rung to run next, so these are held-out, not fresh. Three seeds a line but two for nm and ng, and nm and ng are 16M beyond nightq2 where the n41 forks and the control are 8M, so nm against needs also changes length. n42 is a one-change step on the g998 brains, so gn against control is two changes. The control row (nightq3) and the forks were trained with different seeds. The battery's alive differs from the score rows (46 / 70 / 66 against kept 54 / 71 / 73) because the games and action noise differ. The probe is one seed at one budget.

**Replays and clips.** None kept.

**Links.** 0012 (the first night battery, same world); 0015 (what a script gets in this world and how these brains die over 300 s); 0010 (nothing paid for a meal before the needs reward); `../../ROADMAP.md`, 0.4.1.
