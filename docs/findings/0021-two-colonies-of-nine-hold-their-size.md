# 0021 Two colonies of nine hold their size, untrained or after 8M in their own world, and the one-big-colony brains start them best

date: 2026-11-08 · status: held-out · seeds: 2,000,000 × 256 (held-out) · brains: ab2-3x6-s1/s2, ab2-1x18-s1/s2 (16M on the 0.3 brain c1c16fc46934, from 0016); c29-from18-s1/s2 (8M in 2×9 on ab2-1x18-s1/s2), c29-from36-s1 (8M in 2×9 on ab2-3x6-s1)

**Question.** River's: the main colony world should have two colonies, not three ("visually it makes more sense … at least until we intend to have a significantly bigger world"). How do today's colony brains do with two colonies of nine on the same food and in the same arena, and does training there make them grow?

**World and brains.** The colonies world from 0016 (`colony.toml`: 22 food in patches, nights on 120 s cycles, hatching, nectar flowers, 360 s games, 26 m arena), changed in one thing: 2×9, two colonies of nine with room 3 each, so 24 places in all as in 3×6 (three of six, room 2 each); same nest size and distance from the centre. Brains: the four ab2 brains from 0016, none trained with two colonies, and three c29 brains trained 8M in 2×9 on the recipe they were made with (two from the 1×18 brains, one from a 3×6 brain). 3×6 was rescored on the same code as `-v20` (schema v20) and matches 0016's 3×6 numbers exactly.

**Method.** `terrarium.evals --held-out --episodes 256`, the same games for every brain; the number is a colony's size at 360 s over its size at the start (9 here), mean over colonies and games, with all nims alive at the end summed beside it. Scripts `lab/2026-11-07-colonyab/ab-2x9.sh` and `lab/2026-11-08-colony29/score.sh`.

**Result.** End size over start, and nims at the end of 18 (the 3×6 and 1×18 columns are 0016's):

| brain | trained in | in 3×6 | in 2×9 | in 1×18 |
|---|---|---|---|---|
| ab2-3x6 s1 / s2 | 3×6 | 1.073 / 1.060 (19.3 / 19.1) | 0.992 / 0.956 (17.9 / 17.2) | 0.775 / 0.746 |
| ab2-1x18 s1 / s2 | 1×18 | 1.060 / 1.060 | 1.045 / 1.028 (18.8 / 18.5) | 0.949 / 0.898 (17.1 / 16.2) |
| c29-from18 s1 / s2 | 1×18, then 8M in 2×9 | | 1.063 / 1.019 (19.1 / 18.3) | |
| c29-from36 s1 | 3×6, then 8M in 2×9 | | 0.970 (17.5) | |

Standard errors 0.005 to 0.008. In 2×9 no colony was lost except one of 512 (3×6 s2, and again c29-from36). A meal eaten from the same patch as another colony's nim: 16% of meals in 2×9 for the 3×6 brains, 20% for the 1×18 brains (29% in 3×6). Food a minute is the same everywhere (3.3). After training, colony 0 ends bigger than colony 1 in both c29-from18 runs (10.2 against 8.9, 9.4 against 8.9).

**What it rules out.** That two colonies would sink the colony world: with no training in it at all, two colonies of nine stay at their size (3×6 brains, 0.96 to 0.99) or grow (1×18 brains, 1.03 to 1.05). That a brain trained with three colonies is the best start for two: the 1×18 brains beat them by 0.04 to 0.07 in 2×9, and still do after 8M there. That 8M of training in 2×9, on this recipe, moves them: each c29 brain ends within 0.02 of its parent (−0.02 to +0.02, two to three standard errors either way).

**Limits.** Two seeds a brain untrained and one run a parent trained, held-out seeds only (no fresh block). One food setting and one arena size; River also floated a bigger arena for two colonies, which is the next rung. The ordering 3×6 > 2×9 > 1×18 in nims at the end follows the number of nests, so how far one nest's crowding and longer trips explain it (0016's limit) applies here too. The colony 0 / colony 1 gap after training isn't explained yet: a side of the arena or the colony's index in what the brain sees could carry it. Two colonies were picked as much for how they read on the viewer as for the numbers: watching c29, River found them "certainly VISUALLY much nicer" (fewer colours, bigger groups, room round each nest).

**Replays and clips.** The channel's Colonies line shows the c29 runs with their question (backups `lab/channel/live/`).

**Links.** 0016 (three of six against one of eighteen); 0009; `../../ROADMAP.md`, 0.4.
