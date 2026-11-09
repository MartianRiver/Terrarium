# 0030 The pond nims slow down and stay at the pond to drink once the reward stops paying for turnover and hunger is felt all the time; a sip that needs a slow nim halves their pond speed but isn't what keeps them there

date: 2026-11-09 · status: confirmed · seeds: 9,400,000 × 64 (probe used for reading each rung); confirmed on 9,700,000 × 64, never used for choosing; training seeds 825 to 828 and 836 to 838 · brains: sc5-e12-s2 (start), p1-nl6-s2, p2-h1-s2 and -s3, p3-s2w-s2 and -s3, p4-s1w-s2 and -s3; controls p1c-h0-s2 and -s3, p2c-still4-s2 and -s3, p3c-still2-s2 and -s3 (6M each)

**Question.** 0028 left the pond nims crossing the water at full speed through seven rungs, and a review after it found the reward itself pays for turnover: `needs` 6 pays for each meal or drink by how much hunger it takes away, `needs_lost` 1 charges what the drain took by the same square, so burning water and drinking it back nets about 5× what it cost. Real animals don't work like that: hunger is felt all the time and fades once they're full. With the reward fixed, will the pond nims learn to stop and drink?

**World and brains.** 0028's sc5 world (the nim starts thirsty, moving costs 0.02 a second at full thrust, the e12 effort reward, `[water] still` 4: a sip at speed v is worth `clip(1 − v/4)` of a stopped one), loaded on next with grass off. Each rung changes one thing from the one before and trains 6M from its brain:
- p1, `needs_lost` 1 → 6 (lost water and energy cost what drinking and eating them back pays, so turnover nets nothing), from sc5's parent sc2-e12-s2.
- p2, a hunger term, `[reward] hunger` 1: every second a living nim pays (1 − energy)² and (1 − water)², nothing once full. From p1.
- p3, `[water] still` 4 → 2: at 2 m/s a sip is worth nothing, at 1 m/s half. From p2-s2.
- p4, `still` 2 → 1: only a near-stop drinks well. From p3-s2.

p2, p3 and p4 were each trained again on a second seed from the same parent (836, 837, 838).

Controls, each the rung before with 6M more and nothing changed, on the next rung's seeds: p1c (p1 + 6M, no hunger, seeds 826 and 836, against p2), p2c (p2-s2 + 6M, still 4 kept, seeds 827 and 837, against p3) and p3c (each p3 + 6M, still 2 kept, seeds 828 and 838, against p4).

**Method.** `still_probe.py`, 64 games of 180 s, sampled play as in training, last checkpoint, on seed block 9,400,000 (the one each rung was read on) and again on 9,700,000 for the confirm. A visit is one spell inside the pond; its length runs from entering to leaving. Thrust mean is the median of the brain's raw thrust mean at choices in the pond (the clip is 1).

**Result.** Confirm block 9,700,000; s2 / s3 are the two training seeds. sc5-e12-s2 is from 0028 (block 9,400,000, older code).

| rung | pond thrust mean | pond speed m/s | drink s a living min | visits ≥ 4 s | ≥ 10 s | longest s | alive s a game | deliveries a game |
|---|---|---|---|---|---|---|---|---|
| sc5-e12 (start) | 1.26 | 1.96 | 6.6 | 0 of 293 | 0 | 3.6 | 67 | 2.38 |
| p1 needs_lost 6 | 1.10 | 1.87 | 7.0 | 1 of 310 | 0 | 4.0 | 69 | 3.67 |
| p1c: p1 + 6M, no hunger, s2 / s3 | 0.82 / 1.05 | 1.68 / 1.88 | 5.9 / 8.5 | 6 of 215 / 1 of 380 | 0 / 0 | 5.2 / 4.2 | 68 / 74 | 3.75 / 3.61 |
| p2 hunger, s2 / s3 | 0.74 / 0.60 | 1.44 / 1.22 | 7.9 / 10.7 | 21 of 291 / 46 of 225 | 0 / 2 | 6.0 / 13.1 | 77 / 57 | 3.48 / 2.84 |
| p2c: p2 + 6M, still 4 kept, s2 / s3 | 0.61 / 0.38 | 1.18 / 0.81 | 17.4 / 11.3 | 89 of 507 / 95 of 304 | 15 / 2 | 41.6 / 11.7 | 84 / 84 | 3.00 / 3.56 |
| p3 still 2, s2 / s3 | 0.26 / 0.22 | 0.56 / 0.49 | 14.5 / 19.4 | 95 of 224 / 95 of 289 | 13 / 30 | 24.6 / 71.6 | 62 / 71 | 2.55 / 2.31 |
| p3c: p3 + 6M, still 2 kept, s2 / s3 | 0.26 / 0.22 | 0.54 / 0.48 | 18.9 / 32.9 | 169 of 313 / 194 of 412 | 27 / 100 | 25.8 / 66.6 | 80 / 91 | 2.69 / 1.98 |
| p4 still 1, s2 / s3 | 0.15 / 0.19 | 0.42 / 0.45 | 18.8 / 18.7 | 147 of 262 / 80 of 286 | 51 / 50 | 51.2 / 56.4 | 67 / 64 | 2.36 / 2.17 |

On the reading block (9,400,000) the same order holds: visits of 4 s or more 0 (p1), 8 / 3 (p1c), 30 / 76 (p2), 132 / 115 (p2c), 113 / 118 (p3), 163 / 109 (p4), the longest 6.3 / 16.8, 33.6 / 18.3 (p2c), 23.6 / 58.8 and 52.1 / 49.2 s.

**What it rules out.** That the pond nims can't stop, or can't feel the pond: once the reward stops paying for turnover and feels hunger, they slow at the water and sit, both training seeds at each rung, the longest visits close to a minute. That fixing the turnover alone is enough: p1 barely moves (thrust mean 1.26 → 1.10, one visit of 4 s), because with needs_lost 6 almost nothing pays for being full, only for not losing it. That more training alone would have done it: p1 trained 6M more without hunger stays at 6 and 1 visits of 4 s or more (p1c), where p2 with hunger makes 21 and 46. That a sip needing a slow nim is what keeps them at the water: p2 trained 6M more with sips unchanged sits as often as p3 does (89 and 95 visits of 4 s or more against 95 and 95, both seeds, both blocks), so the long visits came from hunger plus training. What still 2 adds is slowness: pond speed falls from 1.18 / 0.81 to 0.56 / 0.49 m/s, and on one seed the long sits (10 s or more: 2 → 30). It also costs work: p3 lives 62 / 71 s a game against p2c's 84 / 84, and delivers 2.55 / 2.31 against 3.00 / 3.56. Nor did still 1 make p4's long sits: p3 trained 6M more at still 2 sits 4 s or more as often or more (169 / 194 against p4's 147 / 80) and 10 s or more 27 / 100 against 51 / 50, one seed each way, and lives longer (80 / 91 s against 67 / 64). Still 1 slows them a little more in the pond (0.42 / 0.45 against 0.54 / 0.48 m/s).

**Limits.** A pond visit counts time inside the water, not stillness: at p4 the median speed in the pond is still 0.42 m/s, so most long visits are slow wading, not a full stop. Most nims still die before the game ends (alive 64 to 71 s of 180 at p4 on the confirm block, 84 s for p2c). Each control is one 6M chunk on one parent, and the p2c pair shares p2-s2 as parent. p2 also carries the starvation fix of the grass-needs branch (unpaid spend is charged before the death check, the same for drying out), so p1 → p2 changed the code's accounting as well as the reward; the fix only matters to a nim at zero, and the deaths a game moved little. The confirm block has the same games for every brain, one block of 64. Deliveries a game fall from p1 to p3 and p4 (3.67 → about 2.4 on the confirm block): slower nims spend the time at the water instead of carrying, so this world now pays for sitting more than for work. Stopping here is still for drinking, inside the ~20 s horizon; nothing yet asks them to rest in the nest or wait. The hunger term and the reward split are on the grass-needs branch, not on next.

**Replays and clips.** `pond-before-after` (backups `clips/0.4/moments/2026-11-10-stand-still/`, sampled play, block 9,700,000, game 10): p1 crosses the pond eleven times in visits of 1 to 2.6 s; p4 sits in it from 12.6 to 53.4 s. Each half plays in the world its brain trained in (p1 in still 4, p4 in still 1): dropped into the still 1 world, p1 dies at about 25 s in nearly every game, because a fast nim can't drink enough there. The channel's Stand still line lists the runs with their question (backups `lab/channel/live/`).

**Links.** 0028 (seven rungs that didn't stop them, and the review that found the turnover); 0029 (the grass nims, the same reward on grazing); 0027 (the pond world); 0024 (the pinned thrust); `../../ROADMAP.md`, 0.4.
