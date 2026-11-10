# 0039 The night deaths come down to food: 84% of the dead die with the store empty, the untrained brains live a third more with more food, and training in a richer world, a fat reserve or a longer horizon lifts nothing past that

date: 2026-11-11 · status: hint · seeds: 9,980,000 × 256 (the block used to choose the night rungs in 0038; every number here was read on it once) · brains: n58-ctl-s1 and -s2 (n52-ctl + 8M, 0038's control) frozen in five worlds; n66-fat-s1 and -s2, n67-g995-s1 and -s2, n68-jelly6-s1 to -s4 (8M each), against n58-ctl, n64-sleepmore and n64-ctl-t3 and -t4

**Question.** 0038 found that sending the night brains home doesn't keep them alive. What does kill them, and does a world that changes it teach them to live?

**World and brains.** The night world of 0037 and 0038 (60 s night, cold .005, drain .0125, jelly .4 eaten from the store below .6, two nims a colony). The frozen tests change one thing each with no training: no cold, jelly worth .8, jelly worth .6, or a fat reserve (`[fat]` capacity .5, banked above .8 energy, drawn below .5; body next 5182323). Then three rungs, 8M each from n52-ctl, one change each: n66 trains with the fat reserve (seeds 661, 662, against n58-ctl); n68 trains with jelly .6 (seeds 661 to 664, against n58-ctl and the twin controls t3 and t4, which share parents and seeds); n67 trains at gamma .995 (about 40 s of reach) on n63-sleep (0038), against n64-sleepmore, the same parents with 8M more at .99.

**Method.** `mates.py`, 256 games × 300 s, alive at the end, kept / self / both as in 0035. Where the deaths come from: `deaths_fat.py` (backups `lab/2026-11-10-n58home`, output in `dk-ctl-full.txt`) on n58-ctl-s1, 512 nims: when each died, where, the store in its nest at that moment, jelly eaten, dark seconds at home and out, what each carried at nightfall.

**Result.** Where n58-ctl-s1's nims die (281 of 512 dead by 300 s): mostly in the dark, 10 to 50 s into each night (as 0037), a median 6.8 m from their nest, 6% inside it; 255 of the 281 chilled through. At the moment each died, its nest's store was empty for 84% of them (mean 1.2 jelly, 16% with one or more), and the mate was still alive for 51%. The survivors ate 10.9 jelly a nim in the game, the dead 3.1, and came to nightfall carrying an apple 38% of the time against 19%. The survivors are not the ones that stayed home: they spent 108 of their 120 dark seconds out of the nest (the dead 61 of the 65 they lived through in the dark). Energy at nightfall is .66 on average, .59 for those that die.

The same brains frozen, with more food or no cold (s1 / s2, kept / self / both):

| world | n58-ctl-s1 | n58-ctl-s2 |
|---|---|---|
| plain (jelly .4, cold .005) | 45 / 44 / 39 | 53 / 36 / 33 |
| jelly .6 | 62 / 56 / 51 | 77 / 69 / 67 |
| jelly .8 | 68 / 59 / 57 | 80 / 71 / 70 |
| no cold | 64 / 57 / 52 | 78 / 71 / 68 |
| fat reserve .5 | 42 / 41 / 40 | 51 / 32 / 33 |

Half the food bump (jelly .6) buys most of what doubling it does, and as much as taking the cold away; a fat reserve, which only moves the food they eat into a bank, buys nothing.

Trained in those worlds, against matched controls in the same world:

| rung | world scored | s1 | s2 | s3 | s4 | control |
|---|---|---|---|---|---|---|
| n68 jelly .6 | jelly .6 | 53 / 52 / 50 | 74 / 68 / 62 | 61 / 60 / 52 | 75 / 71 / 65 | 62 / 56 / 51, 77 / 69 / 67, 62 / 54 / 49, 69 / 63 / 59 |
| n68 jelly .6 | plain | 41 / 43 / 37 | 50 / 38 / 37 | 45 / 46 / 41 | 53 / 50 / 46 | 45 / 44 / 39, 53 / 36 / 33, 42 / 32 / 33, 53 / 34 / 40 |
| n66 fat | fat | 46 / 43 / 42 | 50 / 44 / 45 | | | 42 / 41 / 40, 51 / 32 / 33 |
| n67 gamma .995 | sleep | 39 / 35 / 33 | 46 / 46 / 43 | | | 44 / 43 / 38, 47 / 41 / 39 |

n68 minus its control in the jelly .6 world: −9 / −4 / −1, −3 / −1 / −5, −1 / +6 / +3, +6 / +8 / +6, a mean of −2 / +2 / +1; the trained brains live in the richer world about as the untrained ones do there. In the plain world the mean is −1 / +8 / +4, self and both up on three of four, inside the 3 to 12 points the training seed alone moves a brain (0038). n66 sits inside that spread in its own world and in the plain one (40 / 43 / 38, 49 / 40 / 36), eating more jelly (7.2 to 8.0 a game against 5.7). n67 is level on s2 and 5 to 8 under on s1.

**What it rules out.** That the night brains die for want of being home: the survivors are out most of the night too, and the dead mostly die with nothing left in the store to come home to. That the world's food is too little: a scripted nim lives through both nights on it (0015), so the shortfall is in how the brains gather and store it. That a richer world teaches them more: n68's four seeds learn nothing past what the food gives the untrained brain. That a bank for the food (fat) or a longer reach (gamma .995, also 0035) helps here.

**Limits.** `hint`: every number is from the block that chose the rungs (9,980,000), scored once. The death analysis is one brain, one seed. Two measures in `deaths_fat.py` disagree: the survivors read no energy lost a dark second while reading nothing eaten in the dark, which can't both hold, so neither is used here. Not settled: why the brains stock too little. One lead, not tested here: the night recipe pays `home` .5 for carrying an apple toward the nest (a shaping term that falls to nothing on delivery) and `stored` 0, so an apple stored at dusk pays only when it is eaten in the dark, 30 to 60 s later, past the brain's 20 s reach. n69 (`stored` .5, four seeds) tests it.

**Replays and clips.** None.

**Links.** 0015 (the scripted nim lives on this food); 0026 (food holds the colonies at their size); 0035 (a longer horizon costs); 0036 (going home at dusk costs the last apple); 0037; 0038 (home doesn't keep them alive).
