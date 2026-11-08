# 0017 The night brains walk straight back out of the nest, fed or hungry, dark or light

date: 2026-11-08 · status: hint · seeds: 8,112,000 × 256 · brains: n43-nm-s1, n43-nm-s2, n45-nm3-s2 (last checkpoints, 8.0M samples)

**Question.** The best night brains die in the dark 6 to 7 m from home, and 44 to 70% of those had been inside the nest that night and left again (0015). What makes a nim that is home in the dark walk out: hunger with an empty store, hunger with jelly there, or does it leave even fed and stocked, because it doesn't read the dark as "stay"?

**World and brains.** The night world of 0014 and 0015 (`nights44/world.toml`: one colony of two, a 60 s night in each 120 s cycle, dusk 10 s, cold 0.005, drain 0.0125 a second, nest radius 1 m), played for 120 s. The three brains are night-trained: n43-nm-s1 and n43-nm-s2 are two of 0014's and 0015's, and n45-nm3-s2 is n43-nm-s2 with 8M more samples of the same needs recipe (where that line stopped climbing: 51% alive over 300 s against its parent's 50%). Weights frozen, 128 note slots, yes/no actions drawn as a coin as in the evals.

**Method.** 256 games a cell, the same games for every brain and condition, seed block 8,112,000 (new for this question). The world clock is set to 60 s, the first full dark, at tick 0 (through the World's clock array), both nims in the nest's middle with an empty crop, and 60 s are played to dawn. Four starts: F energy 1.0 and 6 jelly in the store (fed, stocked), H energy 0.45, under the 0.6 hunger line, and 6 jelly (hungry, jelly there), E energy 1.0 and no store (fed, nothing stored), HE energy 0.45 and no store. Out is a centre further than the nest radius plus 0.5 m, 1.5 m. Controls: the same four starts at dawn (clock 0, dusk falls at 50 s); a hold start, which plays from 0 with both nims held still (thrust, turn and every yes/no zeroed, the notes still running on what they see) until 60 s and then sets the start; and a held-still bound, the clock start with thrust and turn zeroed and jumping off, which prices leaving. Free play from 0 s, no set-up, reads when a nim gets into the nest after 60 s, how long it stays and what it has when it goes. Notes are run kept and wiped for both whenever either stores (`mates.py`'s standard). Scripts and per-game arrays are in the lab folder, outside the repo.

**Result.** From the clock start (60 s, first full dark), notes kept; wiped for both is the same game for game, since nobody stores in the dark:

| start | brain | alive at dawn | left, of 512 | median first leave | re-entered | in nest at dawn |
|---|---|---|---|---|---|---|
| F | n43-nm-s1 | 68% | 512 | 1.58 s | 69% | 7% |
| F | n43-nm-s2 | 91% | 512 | 1.35 s | 93% | 5% |
| F | n45-nm3-s2 | 90% | 512 | 1.30 s | 91% | 6% |
| H | n43-nm-s1 | 62% | 512 | 1.60 s | 67% | 4% |
| H | n43-nm-s2 | 84% | 512 | 1.35 s | 87% | 5% |
| H | n45-nm3-s2 | 83% | 512 | 1.35 s | 85% | 4% |
| E | n43-nm-s1 | 16% | 510 | 2.33 s | 73% | 1% |
| E | n43-nm-s2 | 20% | 511 | 1.40 s | 92% | 3% |
| E | n45-nm3-s2 | 17% | 512 | 1.40 s | 87% | 3% |
| HE | n43-nm-s1 | 0% | 504 | 2.55 s | 44% | 0% |
| HE | n43-nm-s2 | 0% | 512 | 1.45 s | 64% | 0% |
| HE | n45-nm3-s2 | 0% | 511 | 1.45 s | 64% | 0% |

Every start empties the nest: 502 to 512 of 512 leave in all twelve cells, a median 1.3 to 1.6 s after the clock starts (n43-nm-s1 takes 2.3 and 2.6 s with the store empty). They leave fed (energy 0.95 to 0.98 in F and E, all above the hunger line) as fast as hungry, and with six jelly at home as fast as with none. The dawn start, the same four starts with the apples standing, leaves as fast: medians 1.25 to 1.48 s in F, 1.25 to 2.17 s across starts. The hold start agrees with the clock start: first leave 1.45 to 3.25 s, alive at dawn within 6 points of it in every cell.

Free play from 0 s says the same without a set-up. A nim that gets into its nest in the dark (71 to 97% do, by about 67 s) is inside a median 1.2 to 1.3 s and leaves again in 99 to 100% of entries (99.3 to 99.8%), at 87 to 94% fed and 80 to 90% with jelly in the store, and with nothing in the crop. In H, 81 to 86% eat first and still leave at about 0.76 energy: hunger decides eating first, not whether to go.

What leaving costs, from the clock start: 90 to 91% alive at dawn for F (68% for n43-nm-s1), 62 to 84% for H, 16 to 20% for E, 0% for HE. Held still in the nest, F and E are 100% alive at dawn, H 85 to 92%, HE 0% (energy 0.45 at 0.0125 a second is 36 s). Of the nims that die after leaving, 90 to 100% die outside, a median 5.5 to 8.7 m from the nest. In free play, wiped for both is below kept at dawn: 50 against 61% (n43-nm-s1), 71 against 80% and 70 against 78%, 7 to 12 points, a hint on one block.

**What it rules out.** That a nim walks out because it is hungry, or because the store is empty or full: fed and stocked it leaves as fast and as completely as hungry and bare. That it reads the dark as "stay": the dark start empties the nest as the dawn one does. So fixing eating, the hunger line or the store won't stop the walk-out: the nest isn't a place these brains stay in. For a night's survival the nest has to end the trip, and nothing in the brains' training so far makes it.

**Limits.** One seed block of 256 games, three brains from one line (the needs forks of 0014, one of them 8M further on), frozen, so a hint about that family, not about the night. The clock start gives both nims blank notes at 60 s; the hold start, where they have been running notes since 0, agrees, so the blank notes don't explain it. Both nims start on one spawn point, the nest's middle, so a start in the middle isn't a nim that has just walked in. The wiped-against-kept aside is free play only, from one block, and not tested for cause. Doesn't rule out a brain trained under a different reward holding in the nest, nor that the walk-out is a day habit (arrive, unload, go) carried into the night.

**Replays and clips.** None kept.

**Links.** 0012 (the first night battery: the night brain depends on the light); 0015 (the brains die out in the dark, 44 to 70% of them after leaving the nest again); `../../ROADMAP.md`, 0.4.1.
