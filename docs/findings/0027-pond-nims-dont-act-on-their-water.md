# 0027 The pond nims barely act on their water: most pond visits come from their route, most dry ones likely never went in, and only training them thirsty teaches two of three seeds to head for it

date: 2026-11-09 · status: held-out · seeds: 2,000,000 × 256 (held-out) · brains: w7-pay3-s1..s3, w7b-pay3-s1, w7c-pay6-s1 (frozen, measured four ways); w7c-pay6-s2, s3 (deaths and drinks beside W8); w8-thirsty-s1..s3 (8M from the W7c brains with the nim starting at water 0.3)

**Question.** 0025 read the pond nims' ceiling as time in the pond: the same brains lived 13 to 19 s longer in a bigger pond with no training, so crossing the small one at full speed seemed to leave too little time to drink. River watched W7 and saw them "alternating between going to water and going to apples" and never letting their water get low. Do they act on their water at all, or is the pond just on their way? If they do, what would stopping to drink buy?

**World and brains.** W2's pond world from 0023 and 0025 (a 32 m garden, one baby nim, one pond of radius 1.5 m 5 m from the nest, 180 s games, full water lasts about 83 s, a full drink takes 4 s inside the pond). The brains are the W7 family from 0025: W7 (a drink pays 3), W7b (8M more at 3), W7c (8M more at 6). Four frozen variants of the world, one change each: thirst off (`drain` 0), the nim starting thirsty (`water.start` 0.3), drinking faster (0.25 → 0.67 a second, a full drink in one 1.5 s crossing). W8 is W7c's recipe (a drink paying 6) on the W7c brains for 8M, changed in one thing: it trains starting at water 0.3 (`water.start` 0.3), and is scored starting full (the real test) and starting at 0.3. W7b and W7c's own scores against W7 aren't in a finding yet.

**Method.** Held-out games, 2,000,000 × 256, the same games for every brain. Visits are counted by entering the pond: water at the start of a visit, gain and seconds a visit, visits a minute, and apples home a minute (`drinks.py`). Dry deaths (`deaths.py`): for each nim that ran out of water, seconds since it last left the pond (the game's start if it never entered) and its distance from the pond; for the living outside it, by water left, the mean cosine between its velocity and the way to the pond (0 is no pull either way). W8 against W7c uses the same measures plus the tree-home score, paired over games with 95% bootstrap intervals.

**Result.** The frozen brains, in the normal world, with thirst off, starting thirsty and drinking faster:

| brain | visits a min, thirst on → off | apples home a min, on → off | alive at end: normal / start 0.3 / drink 0.67 |
|---|---|---|---|
| w7-pay3-s1 | 2.74 → 2.26 | 3.26 → 4.86 | 0.64 / 0.54 / 0.72 |
| w7-pay3-s2 | 1.65 → 1.18 | 3.13 → 5.24 | 0.38 / 0.18 / 0.45 |
| w7-pay3-s3 | 2.10 → 1.62 | 3.64 → 5.44 | 0.51 / 0.33 / 0.61 |
| w7b-pay3-s1 | 2.89 → 2.46 | 3.34 → 4.61 | 0.72 / 0.54 / 0.76 |
| w7c-pay6-s1 | 2.69 → 2.39 | 3.53 → 4.60 | 0.72 / 0.57 / 0.79 |

With thirst off, 100% are alive at the end and visits fall by 0.3 to 0.5 a minute, so most of the pond visits happen with nothing to drink for: the pond is on their route. A visit takes a median 1.3 to 1.45 s (90th percentile 1.5 to 1.7), the same with thirst off: no brain stops, it crosses at full speed. Water at the start of a visit is a median 0.71 to 0.85, the gain a visit a median 0.15 to 0.19 (a full drink is 1.0), and time under a quarter full is 5 to 13% (0.046 to 0.127). Apples home keep 60 to 77% of their thirst-off number. Starting at 0.3 doesn't send them to the pond: alive at the end falls in all five and apples home fall to 1.3 to 2.2 a minute, water at visit start has a 10th percentile of 0.13 to 0.19. Drinking faster (a full drink in one crossing) adds 4 to 10 points alive at the end, apples home up 0.08 to 0.17 a minute, and the gain a visit stays at a median 0.13 to 0.18: a pass already tops them up, so the time in the pond isn't what holds them.

Dry deaths (256 games a brain): 92, 159, 125, 72 and 71, in the order of the table. The median dry nim had no pond exit on record (83.3 s, counted from the game's start when it never left a pond, a full water's whole life), so most likely it never went in, though the measure can't tell that from a visit right at the start; the 10th percentile died 20 to 40 s after their last visit and the 25th 38 to 58 s (83.3 for w7-s2), and the median died 5.6 to 6.6 m from a pond 5 m from the nest with a sight of 8 m, so it was in sight. Heading toward the pond among nims outside it: the cosine is 0.02 to 0.07 in each water bin below 0.75 and −0.02 to 0.0 at full water, with no rise as water falls; the distance to the pond doesn't shrink either.

W8, trained from start-thirsty, against its W7c parent (apples home a minute; cosine by water left, below 0.25 / 0.25 to 0.5 / 0.5 to 0.75 / full; median water at visit start; dry deaths of 256; alive at the end, start full):

| | apples home, start full | apples home, start 0.3 | cosine toward the pond | water at visit start | dry deaths | alive at end |
|---|---|---|---|---|---|---|
| s1, W7c → W8 | 3.53 → 3.36 | 2.16 → 2.21 | 0.05 / 0.06 / 0.06 / −0.01 → 0.12 / 0.18 / −0.04 / −0.07 | 0.82 → 0.48 | 71 → 77 | 0.72 → 0.70 |
| s2, W7c → W8 | 2.69 → 2.40 | 1.16 → 1.19 | 0.06 / 0.05 / 0.05 / −0.05 → 0.00 / 0.01 / 0.03 / 0.02 | 0.63 → 0.89 | 112 → 188 | 0.56 → 0.27 |
| s3, W7c → W8 | 3.54 → 3.64 | 2.04 → 2.10 | 0.06 / 0.04 / 0.10 / −0.02 → 0.11 / 0.13 / 0.04 / −0.07 | 0.80 → 0.63 | 71 → 76 | 0.72 → 0.70 |

The apples-home changes are all inside their intervals. In s1 and s3 visits a minute fell (2.69 → 1.82, 2.65 → 2.14) and the gain a visit rose (0.18 → 0.28 for s1, 0.19 → 0.24 for s3, in medians): they head for the pond when low, away when full, and drink later and less often. s2 changed none of it (its gain a visit fell to 0.09).

**What it rules out.** That the pond nims drink because they're thirsty. In every W7-family brain, drinking happens in the games whose route crosses the pond, and the long stretches without a pass kill them: the median dry nim most likely never went in. Thirst does move them a little (visits fall by 0.3 to 0.5 a minute with it off), so they aren't blind to their water, just far from acting on it. That time in the pond caps them: 0025's reading of its bigger-pond result ("so time inside the pond on each crossing caps their drinking") is corrected here, because a pass already fills them nearly full and drinking nearly three times as fast, a full drink in one crossing, adds only 4 to 10 points alive; the 13 to 19 s from the bigger frozen pond more likely came from crossing it more often. That a reward for drinking efficiently has anything to shape yet: a drink paying more buys more crossings, not drinking on thirst (W7c-s1's cosine is still 0.05 to 0.06).

The other half of the answer: that nothing can teach them to act on it. Training W8 starting thirsty teaches s1 and s3 to head for the pond as water falls. It doesn't keep more of them alive, though: they cut it closer and die dry as often (71 → 77, 71 → 76), and s2, which learned none of it, got worse (alive 0.56 → 0.27).

**Limits.** Held-out seeds only; the frozen measurements are 256 games of five brains from one family, and three seeds for W8, one run each. "Never entered" is read from the time since a nim last left the pond (the game's start if it never did), not from a drink log. Heading toward the pond is a mean cosine over every moment a nim is moving outside it, so it can't show a nim that decides to go and drifts. W8's seeds differ and the sample is two of three: it is a first sign, not a recipe. The pond is 5 m from the nest in sight; a pond out of sight would ask a different question. What a nim should do when the pond is easy to reach isn't tested here; 0023 and 0025's thirst runs all share this pond.

**Replays and clips.** None recorded yet.

**Links.** 0023 (180 s games teach drinking); 0025 (the pond plateau and the reading this corrects); 0024 (thrust pinned at full, the same brains' speed); 0028 (what unpinning the thrust did for stopping to drink); `../../ROADMAP.md`, 0.4.
