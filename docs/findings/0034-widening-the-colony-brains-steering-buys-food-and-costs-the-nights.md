# 0034 Widening the colony brain's collapsed steering spread buys a little food a minute and costs the nights, more the wider it goes: no reset kept the gain and the colonies

date: 2026-11-10 · status: held-out · seeds: 2,000,000 × 256 (scores, the held-out block, also used for choosing); training seeds 641 and 642 (0.35, 0.10 and the control), 643 and 644 (0.35 more, 0.20) · brains: c29-from18-s1 and -s2 (the parents, 8M in two colonies of nine), c2x9-more-s1 and -s2 (control: 8M more as they were), c2x9-spread010-s1 and -s2, c2x9-spread020-s1 and -s2, c2x9-spread-s1 and -s2 (0.35), c2x9-spread-more-s1 and -s2 (8M more from the 0.35 ones)

**Question.** 0032 found the colony brain's steering had lost its randomness (thrust and turn spread 0.03 to 0.04, against about 0.35 for a fresh brain) and that a reset to 0.35 let it learn to graze. Does the same reset lift a colony by itself in the colony world, and at what cost?

**World and brains.** The colony world the line was trained in: two colonies of nine nims in a 26 m arena, room for three more each (a cap of 12 a colony), 22 food, 360 s games with two nights, hatching and flowers on. The parents are c29-from18-s1 and -s2, which 8M in this world left where they started (end size 0.97 to 1.06 of the start, 8 Nov). Four arms from each parent, 8M samples on the c29 recipe (`train-03.toml`), the same seed in each pair:
- c2x9-more: nothing changed, the matched control.
- c2x9-spread010, -spread020, -spread: thrust and turn spread of the copied checkpoint set to 0.10, 0.20 and 0.35 (the learned `log_std`, nothing else changed).
- c2x9-spread-more: a second 8M from c2x9-spread, no further reset.

**Method.** `terrarium.evals --policy --modes drawn` in the 2x9 world, 256 games of up to 360 s from seed 2,000,000, the same games for every brain, last checkpoints. `--modes drawn` steers thrust and turn by the mean, so deaths in the dark are what the brain learned, not noise from its spread. Food a minute is per living minute. The control pair for each seed ran on the same code but not the same machine (s1 spread and control on the Mac, s2 spread on Alexandria and control on Jellybean).

**Result.** Seeds as s1 / s2. Colony size is at the end of the game (start 9, cap 12); "lost" is colonies with nobody left, of 512; "in the dark" is deaths of the 6,144 nims a game set includes (18 at the start plus those hatched).

| brain | food a minute | food a game | hatched | colony size at end | lost, of 512 | died, % of nims | died in the dark |
|---|---|---|---|---|---|---|---|
| parent c29-from18 | 3.27 / 3.30 | 17.2 / 16.9 | 6.17 / 6.73 | 9.54 / 9.25 | 0 / 0 | 47 / 54 | 898 / 1,042 |
| control, 8M more | 3.29 / 3.31 | 17.1 / 16.9 | 6.95 / 6.69 | 9.50 / 9.28 | 0 / 0 | 54 / 53 | 894 / 970 |
| reset 0.10 | 3.34 / 3.42 | 17.1 / 16.3 | 6.96 / 8.06 | 9.38 / 8.48 | 0 / 3 | 55 / 72 | 915 / 1,808 |
| reset 0.20 | 3.36 / 3.51 | 16.9 / 16.3 | 7.58 / 8.60 | 9.30 / 8.19 | 1 / 6 | 61 / 78 | 867 / 2,207 |
| reset 0.35 | 3.60 / 3.61 | 12.4 / 13.7 | 7.66 / 8.18 | 5.04 / 5.95 | 116 / 94 | 97 / 94 | 3,477 / 3,082 |
| reset 0.35, 8M more | 3.46 / 3.51 | 12.7 / 11.4 | 7.50 / 7.04 | 5.46 / 4.05 | 113 / 191 | 92 / 100 | 3,005 / 4,091 |

Standard errors on colony size are 0.05 to 0.07 for the parents, controls and the 0.10 and 0.20 brains, and 0.12 to 0.13 for the 0.35 ones. After 8M the 0.35 reset's spread was still 0.33 (s1 only).

Against the matched control, food a minute rises 2 / 3% at 0.10, 2 / 6% at 0.20 and 9 / 9% at 0.35. Colony size at the end falls 0.1 / 0.8 at 0.10, 0.2 / 1.1 at 0.20 and 4.5 / 3.3 at 0.35. Dark deaths at 0.10 and 0.20 are flat on s1 (915 and 867 against 894) and about double on s2 (1,808 and 2,207 against 970). Hatching is the one gain that doesn't scale with the reset: on s1 it rises 0.6 to 0.7 at 0.20 and 0.35 only, on s2 it rises 1.4 to 1.9 at every reset and is highest at 0.20.

**What it rules out.** That the reset is free in the colony world, as it was for the grass nims (0032), or that a middle value keeps the gain and the colonies: food a minute rises with the reset and so do dark deaths, and the one value that gives the full food gain (0.35) loses a fifth of the colonies (116 and 94 of 512, none lost in the control). That more training repairs it: 8M more from the 0.35 brains left the nights as bad (lost 113 and 191, in the dark 3,005 and 4,091). That more training alone moves the line: 8M with no reset changes nothing (control against parent, both seeds), while the reset moves it, but along a trade, not up. What it doesn't settle is why the nights are lost; the same reset cost the night brains too (0035), and neither this nor that was looked at nim by nim.

**Limits.** Two seeds, one block of 256 games, and that block is the held-out one used for choosing, so this is `held-out`, not `confirmed`; one control per seed, so the 0.10 and 0.20 gaps (the s1 pair inside a standard error, the s2 pair clear of it) are small next to the 0.35 one. Food a minute counts living minutes only, so with nims dying in the dark its rise is smaller than it looks: food a game falls from about 17 to 12 to 14 at 0.35 and stays level at 0.10 and 0.20, so no reset made a colony eat more over a game. Spread was read from a checkpoint only for the 0.35 s1 brain (0.33 after 8M), not for the other arms, and it is a one-off edit, not a floor: whether a floor kept during training (`[ppo]`) would keep the spread and let the brain learn the nights is untested. The 0.35 brains' second 8M has no matched 16M control (the 8M control was flat, so one wasn't trained). Whether the reset brains keep any colony skill that the score here doesn't measure isn't checked.

**Replays and clips.** None yet.

**Links.** 0032 (the collapsed spread and the grass reset); 0021 (two colonies of nine); 0026 (food, not the brain, holds the colonies at their size); 0035 (the same reset on the night brains).
