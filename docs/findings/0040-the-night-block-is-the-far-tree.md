# 0040 The night block is the far tree: dying nests stock too little because the brains can't see a tree 12 m off, and trained with 12 m sight they live the night 90% of the time

date: 2026-11-11 · status: confirmed · seeds: 9,990,000 (the probes; a block 0038 had confirmed on, reused by mistake) and 9,980,000 × 256 (the block that chose the night rungs, as in 0039); confirmed on 9,940,000 × 256 (0041) · brains: n58-ctl-s1 and -s2 frozen; n70 and n70b (8M each from n52-ctl, seeds 661 and 662), one easier world each, against n58-ctl

**Question.** 0039 found the night deaths come down to food. Why do some nests come to nightfall with too little, and is there an easier world where training teaches them to live, to work back from?

**World and brains.** The night world of 0037 to 0039: one colony of two, nest at the middle, the apple tree scattered up to 12 m from it (`[arena] scatter` 12, so 1 to 14.4 m, median 8.4), vision 4 m, smell off, 60 s nights. The frozen tests use n58-ctl s1 and s2 (0038's control). The grid trains six easier worlds, one change each, 8M from n52-ctl: carry two apples (crop2), 0.05 a second for being alive (alive05), the tree within 6 m (scatter6), carry two plus a 180 s cycle (120 s of light, 60 s of dark) in 240 s games (sink240), the same 180 s cycle in 240 s games (day180e) and vision 12 m (vision12).

**Method.** Probes on 32 to 128 games (seed 9,990,000, scripts in backups `lab/2026-11-11-codex-day`): the state of each nest at first nightfall split by whether its nims live to dawn; forced counterfactuals (4 jelly added to the store at each nightfall, nims sent home and kept there from lights-out, both); the reward each arm collects in the dark; the same split by tree distance; each trip's legs (out, at the tree, back) against the 0015 scripted nim on the same games. The grid: `mates.py`, 256 games × 300 s, alive at the end, each brain in the plain night world and in its own world (made 300 s long), with n58-ctl beside it in both.

**Result.**

| | alive at 300 s |
|---|---|
| n58-ctl, plain night, 32 games, as played | 41% / 50% |
| + 4 jelly at each nightfall | 67% / 92% |
| sent home from lights-out | 39% / 55% |
| both | 91% / 100% |

At first nightfall, the nests whose nims die that night had delivered 1.3 and 1.7 apples against 5.1 and 5.0 for those that live, with 1.0 and 1.7 jelly stored against 7.5. The store is empty at 89% and 81% of deaths against 44% and 43% of the nims at risk at the same moments, so the shortfall comes before the death, not from it. In the dark, going home and eating with the store stocked pays about the same as what they do (−.07 and −.03, neither clear of zero) while keeping 50 more nims in 100 alive: survival is close to invisible to the recipe inside its 20 s horizon, which is why the home rungs (0018, 0019, 0036 to 0038) never lifted it.

The short stock is the far tree. Split by distance (128 games): near (4.3 m) 16.8 deliveries by nightfall, 99% and 92% alive at first dawn; mid (8.5 m) 5.5 and 6.3, 65% and 89%; far (12 m) 3.0 and 4.0, 9% and 36%; distance against deliveries by 60 s −.90 and −.84. On the far games the 0015 script, which knows where the apples are, delivers 6.8 by nightfall and lives 100%. Leg by leg, the brains' walk out to a far tree takes 13 to 20 s at 2.3 to 4 times the straight line against the script's 5 s at 1.0, while the walk back matches it (5.6 to 5.9 s against 6.4): home is sensed and the tree isn't, so every trip out is a search, shortening only to 8 or 9 s by the third.

The grid, alive at 300 s:

| arm | its own world, trained | its own world, n58-ctl | plain night |
|---|---|---|---|
| n58-ctl | | | ~45% (0039) |
| crop2 | 58% / 71% | 59% / 80% | 44% / 44% |
| alive05 | (plain world) | | 45% / 50% |
| scatter6 | 87% / 96% | 91% / 89% | 41% / 45% |
| sink240 | 85% / 86% | 76% / 91% | 39% / 39% |
| day180e | 68% / 76% | 74% / 85% | 45% / 46% |
| **vision12** | **90% / 90%** | 34% / 50% | 32% / 45% |

Every easier world but one rescues the untrained control as much as the trained brains: the world does the work and training in it adds nothing. With 12 m sight the control does worse than in its own world (it never learned to use the far rays), and training there takes both seeds to 90%. Back at 4 m those brains fall to 32% and 45%, where the control is.

**What it rules out.** That the night brains die for want of coming home: home without stock only delays it. That more food, longer days, pay for staying alive or a nearer tree teach them anything: those worlds keep the untrained brain alive about as well. That the far trips are slow at the tree or on the way back: the loss is the walk out.

**Limits.** `hint`: two seeds an arm; the grid is scored on the block that chose the night rungs (9,980,000), once; the probes on 9,990,000, at 32 to 128 games. Scoring each arm in its own world changes the world under the control as well, so the own-world column compares a trained brain to an untrained one in the same world, not to the plain night. Vision 12 m also shows mates and the nest from farther, not only the tree; which of those carries the 90% isn't split. The 12 m world isn't the target: whether it's a step to work back from (vision 8, 6, then 4 m) is the next question. Smell can't stand in for sight here as it is: only food on the ground gives a smell, the tree gives none.

**Replays and clips.** None yet.

**Links.** 0015 (the scripted nim lives on this food); 0018, 0019, 0036, 0037, 0038 (home rungs); 0039 (the deaths come down to food).
