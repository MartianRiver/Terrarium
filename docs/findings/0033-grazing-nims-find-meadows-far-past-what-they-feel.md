# 0033 Grazing nims learn to find meadows far past the 1.5 m they can feel grass, one step at a time: 4.5 and 6 m from what they start with, then 9 and 12 m once they start fuller; a step too far starves them before they find anything, and past 12 m nothing trained, not even half a step

date: 2026-11-10 · status: confirmed · seeds: anchor probe 9,500,000 × 64 and survival 1,000,000 × 64 (both used for choosing); confirmed on 9,740,000 × 64, never used for choosing; training seeds in each run's job.json (976 to 986 for the 9 m rungs on) · brains: g1p-herd6-s1 and -s2 (start, 0031's line in a herd of six), g1far-d45-s1/-s2, g1far-d6from45-s1/-s2, g1far-d6-s1 (skip), g1far-d12-s1/-s2 (jump), g1far-d9-s1/-s2, g1far-d9e10-s1/-s2, g1far-d12e10-s1/-s2, g1far-d12e085-s2, g1far-d15e10-s1/-s2, g1far-d135e10-s1/-s2, g1far-d12more-s1/-s2 (6M each)

**Question.** 0031's grass nims graze meadows 2.5 m from home. Rays don't see grass: a nim feels the cover under it and which way it rises within 1.5 m, nothing further. Can they learn to find meadows further from home than they can sense?

**World and brains.** Nine nims, one colony, 90 s games, grass the only food, six meadows of 1.2 m radius at random angles a set distance from the nest, drawn anew each game; the arena grows with the distance (18 m at 6 m, 24 at 9, 30 at 12, 33 at 13.5, 36 at 15). There's no food at home, so a nim has to find grass on its first trip or starve: with `[energy] start` 0.7 it has about 12 s at full thrust, with 1.0 about 17. Each rung changes one thing from the rung before and trains 6M from its brain: the distance (2.5 → 4.5 → 6 → 9 → 12 m, then 15 and 13.5 m), or the start energy (0.7 → 1.0, and 1.0 → 0.85 on one seed).

**Method.** Two frozen measures over 64 sampled games, last checkpoints. `anchor_probe.py` (0031): the share of the living nims' time spent in a meadow. `terrarium.evals`: the share of the 576 nims (64 games × 9) that die before the game ends. The first probe counted only the nims still alive, so a brain could read 70% in meadows while most of its nims starved (the 6 m brains at 12 m): survival is read beside it from 9 m on.

**Result.** Choosing seeds unless marked; "before" is the parent frozen in the rung's world. Two seeds as s1 / s2.

| rung | change | in meadows, share of living time | died, of 576 | before: died |
|---|---|---|---|---|
| start (g1p-herd6) at 4.5 m | – | 72 / 68% | – | – |
| d45 | 2.5 → 4.5 m | 90 / 87% | – | – |
| d6from45 | 4.5 → 6 m | 91 / 90% | 7 / 13% | – |
| d6 (skip, s1 only) | 2.5 → 6 m in one step | 0% | all | – |
| d12 (jump) | 6 → 12 m | 0 / 48% | 0 / 52 of 64 colonies last the game | 61 / 69% |
| d9 | 6 → 9 m | 88 / 85% | 21 / 38% | 27 / 34% |
| d9e10 | start 0.7 → 1.0, at 9 m | – / 84% | 23 / 14% | 17 / 39% |
| d9e10, back at start 0.7 | – | – | 65 / 27% | 21 / 38% (d9) |
| d12e10 | 9 → 12 m, start 1.0 | – / 85% | 30 / 25% | 38 / 38% |
| d12e10, back at start 0.7 | – | – | 64 / 68% | – |
| d12e085 (s2 only) | start 1.0 → 0.85, at 12 m | – | 31% | 35% |
| d15e10 | 12 → 15 m, start 1.0 | 79 / 76% | 44 / 45% | 43 / 46% |
| d135e10 | 12 → 13.5 m, start 1.0 | 81 / 81% | 38 / 39% | 36 / 29% |

On the fresh block 9,740,000: the 6 m brains at 6 m spend 92 / 90% of their time in meadows and lose 6 / 14%; the 12 m brains at 12 m with start 1.0 spend 84 / 84% and lose 27 / 25%.

**What it rules out.** That grazing nims can only use grass they can feel: step by step they spend about 90% of their lives on meadows 6 m out (four times the 1.5 m feel) and, starting fuller, 84% on meadows 12 m out with three quarters living, on a block never used for choosing. That a big step works if training is long enough: straight from 2.5 to 6 m and from 6 to 12 m, most nims starve before they reach any grass, and there's little left to learn from. That 6M at 9 m with start 0.7 teaches the first trip: 21 and 38% still die, near their parents, all at about 10 s. That more energy alone saves them: frozen at start 1.0 the 9 m brains lose 17 and 39%, dying later instead. With 1.0 and training they learn it (s2 39 → 14%), and the next 3 m too.

**Limits.** 12 m itself has levelled off: 6M more with nothing changed left 31 / 25% dying (30 / 25% before; g1far-d12more-s1/-s2). Two seeds, one world, a nursery with no food at home: every nim gets one try at a blind search whose ground grows with the distance squared while its time is fixed by the start energy, so nothing training past 12 m may be this world's limit rather than the brain's. What they learn with start 1.0 spends it: back at 0.7 one seed loses 65% at 9 m (its parent 21%), the other 27% (38%); stepping the energy down (0.85, one seed) gains 4 points in 6M. The colony world starts nims at 0.8 with a store at home, so the trip there is not a one-try search; this doesn't say how far they'd go there. Meadows sit around colony 0's nest only. The "in meadows" share counts only the living; survival comes from a separate run of the same seeds.

**Replays and clips.** None cut yet. The channel's grass line lists the runs with their question (backups `lab/channel/live/`).

**Links.** 0031 (the grass nims stand to graze); 0032 (the spread reset that let the colony brain graze); `../../ROADMAP.md`, 0.4.
