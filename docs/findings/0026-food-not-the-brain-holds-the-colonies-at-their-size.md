# 0026 Food, not the brain, holds two colonies of nine at their size: with half as much food again they fill every place

date: 2026-11-09 · status: held-out · seeds: 2,000,000 × 256 (held-out) · brains: c29-from18-s1/s2 (from 0021, frozen); c32-s1/s2 (8M on c29 with the arena 32 m); cmid-s1/s2 (8M with both food patches in the middle); chatch-s1/s2 (8M with hatch pay ×4); clong-s1/s2 (16M more of c29's recipe); cent-s1/s2 (8M with the entropy weight ×10)

**Question.** 0021 found that 8M of training in 2×9 left both colonies where they started. River's guess for the night: "the colony setup/run may simply need to be made more complicated before it does anything different". Does any one change to the world or the recipe make the colonies grow, and if not, what holds them?

**World and brains.** The 2×9 world from 0021: two colonies of nine with room for 3 more each (12 places), 22 food in 4 patches, nights on 120 s cycles, hatching, 360 s games, a 26 m arena. Each rung changes one thing and trains c29-from18-s1/s2 for 8M on c29's recipe unless it says otherwise:
- c32: arena 26 → 32 m.
- cmid: both food patches in the middle, so both colonies forage the same ground.
- chatch: `[reward] hatch` 0.5 → 2.0.
- clong: 16M more of the same, 24M in 2×9 in all.
- cent: `[ppo] entropy` 0.0003 → 0.003.

Then two frozen tests, c29 untrained in a changed world: room 3 → 9, and food 22 → 33. Folders: `lab/2026-11-08-colony32`, `-colonymid`, `-colonyside`, `lab/2026-11-09-colonyhatch`, `-colonylong`, `-colonyexplore`, `-colonyroom`, `-colonyfood`.

**Method.** `terrarium.evals --policy --modes drawn --held-out --episodes 256`, the same games for every brain. The number is a colony's size at 360 s, mean over colonies and games (it starts at 9). A trained brain is set against its frozen parent in the same world.

**Result.** Size at the end of 9 (standard errors 0.05 to 0.08), s1 / s2:

| rung | world | frozen c29 | trained |
|---|---|---|---|
| 0021 | 2×9 | 9.57 / 9.17 | c29: (the parent) |
| c32 | arena 32 m | 8.41 / 8.09 | 8.43 / 8.46 |
| cmid | shared ground | 10.37 / 10.18 | 10.40 / 10.12 |
| chatch | hatch pay ×4 | 9.57 / 9.17 | 9.53 / 9.27 |
| clong | 2×9, 16M more | 9.57 / 9.17 | 9.39 / 9.14 |
| cent | entropy ×10 | 9.57 / 9.17 | 9.59 / 9.09 |
| room 9 | 18 places, frozen only | 9.40 / 9.00 | |
| food 33 | half as much food again, frozen only | **11.98 / 11.96** | |

Food eaten a minute stayed between 3.27 and 3.37 for every brain in 2×9, frozen or trained. In 2×9 the colonies peak at 11.5 of their 12 places, and 47% / 54% of all nims that lived died in a game. Given room for 18, they hatched about 2.7 more nims each, and deaths in the dark nearly doubled (911 → 1773, 1014 → 2278); they ended a little smaller. With 33 food, deaths fell to 12% / 13%, and food a minute rose to 3.9; both colonies of both seeds fill all 12 places in almost every game.

Colony 0 ends bigger than colony 1 for every brain (+1.38 ± 0.37 nims for c29-s1, 2×9, 128 games). A frozen test that swaps the nests, breaks ties at random and takes out the two fixed blocks (`lab/2026-11-08-colonyside/report.md`) splits that into about 0.84 ± 0.28 from the arena (the blocks aren't symmetric under a half turn, so the two nests see different ground) and about 0.54 ± 0.28 from same-tick ties at food (about 6 a game between colonies, all won by colony 0, the lower index). Neither is learned (QUIRKS, a known bug); colony totals aren't affected.

**What it rules out.** That two colonies of nine need more training (24M is no better than 8M), a harder arena, a fight over shared ground, more pay for hatching, or more exploration to grow: across these five rungs, ten runs, one moved (c32-s2, +0.37 in the bigger arena). That room to grow was the cap: given 18 places they hatch more and lose more. That colony 0's lead is something the brains learned.

**What it shows.** The 22-food world feeds about nine nims a colony. However well a brain does, a colony that hatches past what the food supports loses as many in the dark as it gained. With half as much food again the same untrained brains fill every place, so every rung tonight ran against a food cap that no change to the brain could show through. The next rung keeps 33 food and gives room for 18 (cfr, running), so that neither cap binds.

**Limits.** Held-out seeds only (`terrarium.evals` has no `--seed` yet, so no fresh block). Two seeds a rung, one run a seed; one recipe (c29's). The food test is frozen only: whether training at 33 food helps couldn't show, because the frozen brains already fill all 12 places there. A colony's size at 360 s is one game's end; a world that feeds more may also make nights matter less.

**Replays and clips.** The channel's Colonies line shows each rung's runs with their questions (backups `lab/channel/live/`).

**Links.** 0021 (two colonies of nine hold their size); 0016 (three of six against one of eighteen); `../../ROADMAP.md`, 0.4.
