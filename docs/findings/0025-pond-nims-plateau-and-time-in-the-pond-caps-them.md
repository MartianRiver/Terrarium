# 0025 The pond nims level off at 115 to 150 s of 180: more training, a bigger pond, a longer horizon or an unpinned thrust barely lift them, and paying three times as much for a drink lifts all three

date: 2026-11-09 · status: held-out · seeds: 2,000,000 × 256 (held-out) · brains: w2b-180-s1..s3 (from 0023); w2c-180-s1..s3 (8M more on W2b, same world); w4-r25-s1..s3 (8M with the pond 2.5 m, s1/s2 from W2c, s3 from W2b); w5-g995-s1..s3 (8M with gamma .995, same parents as W4); w6-thrust-s1..s3 (8M with the thrust head started fresh, same parents); w6b-thrust-s1..s3 (8M more on W6); w7-pay3-s1..s3 (8M with a drink paying 3, same parents as W4)

**Question.** 0023 left the pond nims learning to drink but half still dying of thirst by 180 s, with two seeds of three still gaining. What lifts them further: more of the same, an easier pond to learn on, looking further ahead, letting them slow down, or paying more for a drink?

**World and brains.** W2's world from 0023 (mid2's 32 m garden, one baby nim, thirst, one pond of radius 1.5 m 5 m from the nest, 180 s games, full water lasts about 83 s, a full drink takes 4 s inside the pond). Each rung changes one thing from W2's recipe and starts from the best brain a seed so far:
- W2c: 8M more of the same.
- W4: the pond grows to radius 2.5 m while training, then the brains are scored back at 1.5 m.
- W5: gamma 0.99 → 0.995. On 0.2 s steps that's a horizon of about 40 s instead of 20; a full drink lasts about 83 s, so the old horizon can't see thirst coming.
- W6: the thrust head starts fresh (`[start] fresh = ["thrust"]`): its weights, bias and spread are reset, so the brain can learn to slow down. W6b: 8M more of W6's recipe on the W6 brains.
- W7: `[reward] needs` 1.0 → 3.0: a full drink pays about 3 instead of about 1, against about 2.5 a game for apples home and −1 for dying.

Worlds and scripts: `lab/2026-11-08-water2/` (W2c), `lab/2026-11-08-pondsize/` (pond 2.5, W4), `lab/2026-11-09-watergamma/` (W5), `lab/2026-11-09-waterthrust/` (W6, W6b), `lab/2026-11-09-waterpay/` (W7).

**Method.** `terrarium.games tree-home --config` W2's world, held-out 2,000,000 × 256, the same games for every brain, scored with the tree games' water numbers (seconds alive, alive at the end, water drunk, what the dead died of). Each brain is set against its own parent; differences are paired over games with 95% bootstrap intervals.

**Result.** Seconds alive of 180, against the parent:

| rung | s1 | s2 | s3 |
|---|---|---|---|
| W2c, 8M more | 141.9 → 145.6 (+3.6 [−0.3, +7.7]) | 115.3 → 113.3 (−1.9 [−6.1, +2.1]) | 134.8 → 136.1 (+1.3 [−2.1, +4.7]) |
| W4, learnt on a 2.5 m pond, scored at 1.5 m | 145.6 → 133.3 (−12.3 [−16.6, −8.1]) | 113.3 → 117.2 (+3.9 [+0.0, +7.7]) | 134.8 → 131.7 (−3.1 [−6.5, +0.4]) |
| W5, gamma .995 | 145.6 → 151.8 (+6.2 [+1.9, +10.4]) | 113.3 → 115.4 (+2.1 [−2.6, +7.1]) | 134.8 → 135.0 (+0.2 [−3.0, +3.8]) |
| W6, thrust head fresh | 145.6 → 150.0 (+4.4 [+1.2, +7.8]) | 113.3 → 117.6 (+4.2 [−0.4, +8.6]) | 134.8 → 137.2 (+2.4 [−1.1, +6.2]) |
| W6b, 8M more on W6 (against W6) | 150.0 → 152.4 (+2.4 [−0.4, +5.5]) | 117.6 → 117.1 (−0.4 [−3.9, +2.9]) | 137.2 → 143.8 (+6.6 [+3.1, +10.2]) |
| W7, a drink pays 3 | 145.6 → 151.1 (+5.6 [+1.3, +9.9]) | 113.3 → 124.4 (+11.1 [+7.1, +15.0]) | 134.8 → 141.1 (+6.3 [+2.8, +9.8]) |

Share dead of thirst after W5: 34%, 75%, 57%; the rest were alive at the end, so none starved. Apples home a minute stayed between 3.1 and 3.8 for every brain; W4 brought 0.1 to 0.4 more home when scored on the 2.5 m pond. After W6 the thrust spread stays about 0.58 (the parents' 0.15), and W6 scores the same steered by its mean or drawn from its spread (s1 150.0 against 149.8). Unlike the night brains (0024), unpinning thrust here costs no apples (3.67 / 3.32 / 3.59 after W6). W6b-s3's gain came with fewer apples (3.82 for its W2b parent, 3.37). After W7, dead of thirst 36%, 62%, 49% (the parents 43%, 77%, 57%), apples 3.32 / 3.22 / 3.74.

The same brains frozen, with the pond 1.5 → 2.5 m and nothing trained: W2b 141.9 → 154.7, 115.3 → 128.7, 134.8 → 153.9; W2c s1 145.6 → 159.5, s2 113.3 → 129.5. They gain 13 to 19 s, against 4.8 s for random play (88.9 → 93.7), and drink 0.28 to 0.51 of a full drink more.

**What it rules out.** That the pond nims are still climbing on this recipe: 8M more moved none of the three seeds clear of noise. That a bigger pond to learn on carries over to the small one: on s1 it cost 12 s. With drinking made easy, training traded water for apples. That a horizon too short to see thirst is what holds them: doubling it moved one seed of three, by 6 s. That pinned thrust alone is what holds them: a fresh thrust head lifts all three seeds a little (2 to 4 s) and 8M more adds 0 to 7 s, the same size as W2c, W4 and W5. Across those five rungs each seed stays near its own level (about 150, 117 and 135 s), so which seed a brain grew from matters more than any of these levers.

**What it shows.** What a drink is worth is the lever that moves them. A drink paying 3 instead of 1 is the only rung clear of noise on all three seeds. It lifts s2, the seed stuck near 117 s through every other rung, by 11 s. Apples hold, a little down on s1.

Beside that, the same brains live 13 to 19 s longer in a bigger pond without any training. So time inside the pond on each crossing caps their drinking: a full-speed nim crosses 1.5 m in about 1.5 s, and a full drink takes 4 s. In the night brains, thrust was pinned at full in every situation tested (0024). Unpinning it lifted them only a little, so the cap is time in the pond, but not only because of top speed.

**Limits.** Held-out seeds only; three seeds a rung; one run a seed. Time spent in the pond per visit and the thrust used there weren't measured directly; the cap is read from the bigger frozen pond. W4 and W5 started s3 from W2b, because W2c-s3 wasn't better. W7 is one 8M chunk at one pay; whether more pay or more training at it keeps lifting them is running (W7b 8M more at 3, W7c a drink paying 6).

**Links.** 0023 (180 s games teach drinking); 0024 (thrust is pinned); 0014 (the needs reward); `../../ROADMAP.md`, 0.4.
