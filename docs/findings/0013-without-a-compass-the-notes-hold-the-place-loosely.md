# 0013 Without a compass the notes hold the tree's place three times more loosely, and are worth less

date: 2026-11-07 · status: hint · seeds: 8,109,000 (scores), 8,103,000 (decode) · brains: tb-s1, s2, s3 and tbnc-s1, s2, s3 (one family, from na-lam99-s2)

**Question.** The notes hold the tree's place in the world's frame, not the body's (0004), which a brain can only keep if it knows which way it faces. Does taking the compass away take the remembered place, and what the notes are worth, with it?

**World and brains.** The burrow world of 0003 (`[tree] start` 1.5, `burrow`, tree ±12 m, nest 0.7 off the middle, 32 m, 90 s). `tb`-s1 to s3 are the 8M chunks of 0003 from na-lam99-s2. `tbnc`-s1 to s3 are the same chunk again, same parent, world, training and seeds, with `[home] compass = false`, so `compass_sin` and `compass_cos` read 0. Each scored and decoded in its own world.

**Method.** Apples home a minute over 256 games from seed 8,109,000, notes kept and wiped on unloading, paired by game with a 95% bootstrap (same games for both: the compass changes no draw). Then the decode of 0004: 3,000 frozen games from seed 8,103,000, a ridge read of the tree's offset from the nest from the notes at the first choice after each deposit, trunk out of sight, held out by whole game; medians of the error. Picker 5.54, searcher 2.59.

**Result.**

| seed | compass: kept / wiped (gap) | no compass: kept / wiped (gap) | kept, no compass less compass | gap change | notes read the tree to (compass → none) | senses alone |
|---|---|---|---|---|---|---|
| s1 | 3.84 / 3.20 (+0.64) | 3.29 / 2.68 (+0.61) | -0.55 [-0.73, -0.34] | -0.03 [-0.24, +0.20] | 1.18 m 4.8° → 3.61 m 28.3° | 6.67 → 5.51 m |
| s2 | 4.23 / 3.58 (+0.65) | 3.38 / 3.22 (+0.16) | -0.85 [-0.97, -0.74] | -0.49 [-0.62, -0.36] | 1.39 m 6.1° → 3.70 m 29.1° | 6.64 → 5.64 m |
| s3 | 4.24 / 2.99 (+1.26) | 3.40 / 3.04 (+0.36) | -0.85 [-0.97, -0.72] | -0.90 [-1.14, -0.66] | 1.42 m 5.4° → 3.68 m 29.2° | 6.70 → 5.65 m |

On the first trip out, where both have one deposit behind them, the place reads to 1.72–2.01 m with the compass and 5.05–5.33 m without. In the body's frame neither reads better than the senses (about 10 m with the compass, 8 m without).

**What it rules out.** That the compass is a free extra: in every seed the brain without one brings home 0.55–0.85 fewer apples a minute with its notes, and its notes place the tree about three times more loosely. It also rules out the strong form of the prediction, that without a compass the notes would be worth nothing: every gap stays above 0, and the notes still place the tree better than the senses do, so something else (likely the walls and the off-centre nest, seen by the rays beside the way home) gives a rough fix on which way it faces. s1's notes are worth as much without the compass while holding the place as loosely as the others, so what its notes do for it isn't all in this read.

**Limits.** One family and one 8M chunk each; the parent had a compass, so this is the compass taken away, not a brain that never had one. In this world the tree lies to one side of the nest (four of eight sectors), so bearings span a narrow range, and holding out a whole sector of the garden fails with the compass too (2.9–3.2 m), unlike the centred nest of 0004. The brains without a compass make fewer deposits (14,868 to 17,606 for s1), so the later-trip samples differ; the first-trip column is the even one. The decode is linear: a place held in a form a ridge can't read wouldn't show.

**Replays and clips.** None kept.

**Links.** 0003 (the burrow world), 0004 (the notes hold the tree's place), `../brain.md` (the compass, `[home] compass`); the idea came from the 7 Nov review (a compass ablation, three seeds of 8M).
