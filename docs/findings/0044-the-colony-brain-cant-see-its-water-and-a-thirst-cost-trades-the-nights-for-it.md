# 0044 The colony brain can't see its water, barely moves in training, and a thirst cost trades the nights for a drink

date: 2026-11-12 · status: hint · seeds: 8,127,000 × 32 (every probe, the pond start and the battery's 64 games); training seeds 702 to 705 · brains: c2x9-more-s1 (the donor), m3-ctl, m3-wcur-s1b (m3b), m4-h03, m4-h10, m5-h100, m6-wake, m6-wake-h100, m7-wake-lr2e4, m8-wake-sp20, m8-wake-sp35, m9-all-lr1e4 (24M), m10-wrest, m11-wrest-lr5e5, m12-all-wrest (12M), all `-c128-…-s1`, 8M each unless noted; the `ranger` script

**Question.** 0043 left every brain dead in the main world, mostly of thirst, and the colony brain alive once the water was off. What keeps it from learning to drink, and what does learning it cost?

**World and brains.** `main-world.toml` (0043): a full water bar lasts 83 s, the first dusk is at 50 s and a 60 s night takes .72 of the bar. Every run starts from c2x9-more-s1 on the colony line's own recipe (0.1 s choices, gamma .999, lam .9, lr 5e-5, kl_stop .02), which pays for food, stores and hatching and nothing for a drink: thirst shows only as a death (−0.5). The changes, one or more a run: a thirst and hunger cost every second (`[reward] hunger`, 0030's term, .03 to 1); the new inputs woken (the donor never had water, grass, cold or a pond ray, so those first-layer columns load at zero; `wake.py` gives them random weights of norm 1 and takes their usual value out through the bias); the steering spread set back to .2 or .35 (0032); lr 1e-4 or 2e-4; and a world where water drains at half when still and a fifth asleep, as energy already does (`[water] rest .5`, `asleep .2`, branch water-rest).

**Method.** Each brain frozen, played on its steering's mean (`drawn`: yes/no actions tossed, no steering spread), 32 games × 360 s (64 colonies), seed 8,127,000, in the world it trained in; deaths split by cause and, for thirst, by where and when. A pond-start test puts five of a colony's nims in the pond at water .2 and reads their water after 1 to 60 s. The skills battery (fixed, 64 games) on the main ones: grazing standing, apples home a minute from the tree, the night cohort alive at dawn. The first-layer column norms of every checkpoint, and m9 frozen at 8, 12, 16 and 20M.

**Result.**

| brain | world | colonies alive of 64 | deaths: thirst / chilled / starved | drank | apples a colony | battery: graze / tree / night |
|---|---|---|---|---|---|---|
| donor | main | 0 | 645 / 11 / 38 | 34% | 5.8 | 25% / 2.21 / 49% |
| m3-ctl, own recipe / m3b, 4M at half the drain then 4M | main | 0 / 0 | 663 / 10 / 28, 654 / 8 / 25 | – / 31% | | |
| m4, hunger .03 / .1 | main | 0 / 0 | 648 / 9 / 22, 639 / 7 / 23 | 35 / 36% | | |
| m5, hunger 1 | main | 0 | 589 / 18 / 26 | 33% | 2.55 | |
| m6, woken | main | 0 | 644 / 10 / 40 | 36% | 5.67 | |
| m7, woken, lr 2e-4 | main | 0 | 53 / 19 / 504 | | 0.03 | 0% / 0.01 / 0% |
| m8, woken, spread .2 / .35 | main | 0 / 0 | 681 / 1 / 9, 683 / 0 / 7 | | 6.17 / 7.44 | 24% / 2.39 / 56% (.2) |
| m9, woken, spread .2, hunger 1, lr 1e-4, 24M | main | 0 | 27 / 345 / 204 | 59% | 0.05 | 0% / 0.16 / 0% |
| donor | water-rest | 4 | | | | |
| m8, spread .2 | water-rest | 14 | | | 8.58 | |
| m10, from m8, lr 1e-4 | water-rest | 15 | 724 / 0 / 25 | 30% | 11.19 | 16% / 1.56 / 20% |
| m11, from m8, lr 5e-5 | water-rest | 22 | 731 / 0 / 21 | 33% | 12.81 | 22% / 2.63 / 63% |
| m12, m9's recipe, 12M | water-rest | 0 | 131 / 390 / 58 | 56% | 1.73 | 2% / – / 9% |
| `ranger` (16 games, 32 colonies at .012) | main / water-rest | 31 of 32 / 64 | | | | |

- The donor can't see its water. Its first-layer column for water has norm .01 and the pond ray .01 (energy 3.3, ray distance 5.2); grass, chill and height are 0. In the pond start it walks out within 3 s (2% still in the pond) at water .2 and at water 1.0 alike, and so do m3 and m4; m4-h10's water column reached .06 in 8M. A brain from the pond line (p4t, water .62, pond .54) lives in no colony here either (0 of 32).
- Training barely moves it. At lr 5e-5 the woken columns were still norm 1.0 after 8M, and the whole brain moved 2.45% (relative weight change); at lr 2e-4 2.75%, since kl_stop ends each update at the same step whatever the rate. m7, the one that moved most where it matters, is the first to sit in the pond (43% at 3 s, water .2 to .65 by 5 s) and lost every other skill.
- Most thirst deaths are at home in the dark: 523 of m8's 690. A nim at home at dusk with less than about .75 water dies in the night, doing what the night line taught it.
- A thirst cost every second teaches drinking and then pulls them out at night. m9 at 8 / 12 / 16 / 20M: thirst 280 / 79 / 36 / 12, chilled 32 / 207 / 206 / 218, share of the dark spent at home .81 / .16 / .03 / .004, apples 4.2 / 5.0 / 2.3 / 1.1. In the world where water rests too (m12) the same recipe leaves home in the dark the same way (.03 of the dark at home).
- Water that rests like energy is what lets colonies live: the donor frozen goes from 0 to 4, m8 frozen to 14, and m11's 8M there to 22, keeping grazing, the tree and the night on the battery and gaining on the last two. The battery's pond test isn't kept: water drunk a game falls from the donor's .22 to .03 (m8) and .02 (m11), with 86 to 88% never reaching the pond (donor 70%). m11 still drinks no more than the donor (33%), and thirst is still nearly all its deaths, later. m10, the same at twice the rate, loses the nights (cohort 20%).

**What it rules out.** That more of the own recipe would teach drinking: it pays nothing for a drink and, at lr 5e-5 with kl_stop .02, hardly changes the brain. That a thirst cost fixes it alone: blind (m5) it costs apples and teaches nothing; with the inputs woken it teaches drinking and costs the nights, then the foraging. That the water-rest world stops that trade: m12 makes it there too. That the spread reset is what costs the colony brain its grazing, tree or night here: at .2 it keeps them (m8, m11), against 0034's night brains.

**Limits.** `hint`: one seed a run and one block, 32 games; m11 was picked among about ten runs on the same block it's reported on, so 22 of 64 needs a fresh block before anything is built on it. The water-rest world is easier, not the main world; 4 to 14 of its colonies come with no training at all. The battery and the pond start ran on the same block. The runs change more than one thing at a time (they were a break-it grid, not a ladder), so which part of m9's recipe forgets (hunger 1 or the doubled lr) is read from m10 against m11 and m12 only. `wake.py` took the pond ray's usual value as 0 where an empty ray reads 1, so the woken brains weren't exactly the donor at the start (frozen at no drain they still kept 16 of 16 colonies). The probes, the pond start and the battery's tree and night play the steering without its spread (`drawn`; the battery samples it for grazing and the pond), while training samples it, so a spread reset shows less in them than in training. `ledger.py` and `budget.py` didn't know water rests until the water-rest branch.

**Replays and clips.** None kept.

**Links.** 0043 (the main world can be lived in; the colony brain lives with the water off); 0030 (the pond nims drink once hunger is felt all the time: in a world with no night); 0032 and 0034 (the collapsed spread and what resetting it costs the night brains); 0007 (a cost felt now outweighs a death far off, the same pull as m9's); 0023 (180 s games teach drinking).
