# 0023 With a pond in sight, 90 s games don't teach drinking and 180 s games do, but half still die of thirst

date: 2026-11-08 · status: confirmed · seeds: 2,000,000 × 256 (held-out), 8,114,000 × 256 (fresh) · brains: mid2-s1..s3 (frozen parents, no water in training); w1-pond-s1..s3 (8M on them, 90 s pond games); w2-180-s1..s3 (8M more, 180 s); w2b-180-s1..s3 (8M more, 180 s)

**Question.** River's: "i wanna see progress with the water". A nim now gets thirsty and dies when its water runs out; one pond sits in sight of home. Does it learn to walk to the pond and drink when it's thirsty, and keep bringing apples home?

**World and brains.** mid2's world (0004: one baby nim, the apple tree centred in a 32 m garden, burrow, apples carried home one at a time), changed in one thing for W1: thirst and one pond (radius 1.5 m) 5 m from the nest, in sight of home. The baby pays 1% of every cost, water's drain too, so full water lasts about 83 s; it fills at 0.25 a second while the nim is inside the pond, at any speed, so a full drink takes 4 s inside. The `needs` reward pays a drink by its fall in thirst squared (#144). W1 trained the mid2 brains 8M in 90 s games; W2 trained each W1 brain 8M in 180 s games, the one change; W2b 8M more in the same world. Worlds: `lab/2026-11-08-water1/world.toml`, `lab/2026-11-08-water2/world.toml`.

**Method.** `terrarium.games tree-home --config` W2's world (180 s games), held-out 2,000,000 × 256, the same games for every brain, one nim a game, scored with the tree games' water numbers (branch tree-water-numbers): seconds alive, alive at the end, water drunk, and what the dead died of. Each seed's chain is set against its own frozen parent; differences are paired over games with 95% bootstrap intervals. Script `lab/2026-11-08-water2/score-water.sh`.

**Result.** Seconds alive of 180 (alive at the end, share dead of thirst):

| seed | mid2 (frozen) | W1, 90 s | W2, 180 s | W2b, 180 s more |
|---|---|---|---|---|
| s1 | 105.8 (18%, 82%) | 113.2 (21%, 79%) | 131.4 (45%, 55%) | 141.9 (53%, 47%) |
| s2 | 107.3 (19%, 81%) | 111.2 (22%, 78%) | 117.6 (31%, 69%) | 115.3 (28%, 72%) |
| s3 | 110.1 (21%, 79%) | 112.1 (24%, 76%) | 123.3 (34%, 66%) | 134.8 (43%, 57%) |

Random 88.9 s (0%, 100%, drinks 0.07); the scripted picker, which never looks for water, 92.3 s (9%, 91%). Water drunk a nim rises with seconds alive (s1 0.40 → 0.52 → 0.93 → 1.13 of a full drink). Nobody starved: every death was thirst. Apples home a minute held level (W2b 3.46 / 3.12 / 3.71 against the parents' 3.34 / 3.09 / 3.34; picker 4.00).

W2b against its parent, seconds alive: s1 +36.1 [+30.1, +42.0], s2 +7.9 [+3.1, +12.7], s3 +24.7 [+19.4, +30.0]. W2 against W1: +18.2, +6.4, +11.2 (all intervals above 0). W2b against W2: s1 +10.5 [+6.1, +15.5], s3 +11.5 [+7.8, +15.3], s2 −2.4 [−5.9, +1.0].

On the fresh block 8,114,000 (never used for choosing), W2b against its parent: s1 +34.6 [+28.6, +40.4], s2 +7.3 [+3.1, +11.9], s3 +29.6 [+24.3, +35.1]; W2 against W1 +18.2, +6.5, +14.5, all above 0; every death thirst, apples home level (W2b 3.22 / 3.23 / 3.64 against 3.27 / 3.04 / 3.26).

**What it rules out.** That a pond in sight is enough to teach drinking in 90 s games: W1 adds 2 to 7 s over the frozen parents, because a nim that never drinks still lives about 83 s of 90, so thirst barely costs. That the tree skill is lost to learn water: apples home stay level through all three chunks while the nims live longer. That drinking has levelled off everywhere: two seeds of three were still gaining about 10 s a chunk at 24M.

**Limits.** Three seeds, one pond setting, one nim a game. About half the nims still die of thirst by 180 s, so this is learning to drink, not drinking reliably. A full drink takes 4 s inside the pond, and the night brains' thrust was found pinned at full in every situation tested (lab/2026-11-08-thrust); if the water brains share it, slowing down in the pond is rarely tried, which could be what caps drinking. Not measured here: time spent in the pond per visit, and whether nims head for the pond more when thirsty.

**Replays and clips.** The channel's Water line shows the W1, W2 and W2b runs with their questions (backups `lab/channel/live/`).

**Links.** 0008 (180 s games cost the meals-free brains nothing); 0014 (the needs reward); `../../ROADMAP.md`, 0.4.
