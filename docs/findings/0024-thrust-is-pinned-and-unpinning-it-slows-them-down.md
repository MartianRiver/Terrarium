# 0024 The night brains' thrust is pinned at full everywhere, and unpinning it slows them down instead of keeping them home

date: 2026-11-08 · status: hint · seeds: 9,300,000 × 64 (thrust check), 2,000,000 × 256 (n50 scores) · brains: n49-lost-s1, -s1b, -s2, -s2b and their parents n43-nm-s1, -s2 (thrust check); n50-thrust-s1, -s2 and n51-bound-s1, -s2 (2.0M each on n43-nm-s1 and -s2), anchors n49-lost-s1 and n43-nm-s1

**Question.** 0017 to 0022: the night brains walk straight back out of the nest, and five different rewards haven't changed it. A reading from the code (a Codex review of 0022): the brain's steering means are unbounded and the world clips actions to [−1, 1], so a thrust mean well above 1 can't be pushed down by the policy gradient, and its small noise never samples stopping. Is thrust pinned like that, and does unpinning it, by starting the thrust output over or by pulling its mean back to the edge, let them learn to stay?

**World and brains.** The night world of 0020 and 0022 (one colony of two, the apple tree with burrow, 60 s nights in 120 s cycles, the chill sense), with an off `[water]` section added so the current loader reads it. n50 is n49's recipe on the n43 parents, changed in one thing: `[start] fresh = ["thrust"]`, which sets the thrust output's weights, mean and spread back to a new action's; 2M samples as a first look. n51 is n49's recipe with a loss that pulls a thrust mean past ±1 back to the edge (`[ppo] bound` 1.0 on thrust, branch action-bound, scratch), the one change; 2M, the same seeds as n50.

**Method.** Thrust check (`lab/2026-11-08-thrust/thrust_check.py`, `day_check.py`): 64 games from seed 9,300,000, sampled play as in training, recording at every choice the raw thrust mean, its spread and the chance of a sampled thrust under 0.2, for each nim in its own nest at night (107 to 123 entries a brain), outside by day and in the nest by day. n50: `mates.py` at 300 s and 180 s on 2,000,000 × 256 as in 0022, with n49-lost-s1 and n43-nm-s1 rescored beside it on today's code (both match 0022 to the point).

**Result.** Thrust mean (median) and the chance of a thrust under 0.2, per situation; then n50's share alive at the end ("both" row):

| brain | outside by day | in the nest by day | in the nest at night |
|---|---|---|---|
| n49-lost-s1 / -s2 / -s1b / -s2b | 3.53 / 3.57 / 3.52 / 3.40, 0.00 | 1.58 / 2.62 / 1.65 / 2.47, 0.00–0.09 | 1.76 / 2.87 / 1.72 / 2.54, 0.00–0.02 |
| n43-nm-s1 / -s2 | 3.60 / 3.53, 0.00 | 1.54 / 2.74, 0.01–0.06 | 1.71 / 2.96, 0.00–0.02 |

| brain | 300 s | 180 s | apples home (300 s) |
|---|---|---|---|
| n50-thrust-s1 / -s2 | 4% / 0% | 6% / 0% | 0.46 / 0.01 |
| n51-bound-s1 / -s2 | 3% / 0% | 6% / 0% | 0.76 / 0.12 |
| n49-lost-s1 (anchor) | 42% | 56% | 4.22 |
| n43-nm-s1 (parent) | 42% | 54% | 3.82 |

The thrust spread is 0.15 in every brain (log −1.9), turn's 0.03. The mean is above 1 on 100% of choices outside by day and 72 to 96% in the nest, so the thrust the world plays is full on most choices. Nims leave the nest in a median 0.8 to 1.0 s, day or night: about the time it takes to cross it at full speed. In training, n50's return fell from n49's +5 at its start to −1.6 and −2.8, and game length from about 120 s to 88 s; over 2M s1 climbed back to +0.3 and s2 didn't. After 2M the thrust mean outside by day is 0.33 for n50-s1 (spread 0.61, a new action's) and 0.41 / 0.80 for n51-s1 / -s2 (spread 0.15), against 3.60 for their parent; in the nest it sits near 0 (−0.33 to −0.02) and they still leave, in a median 0.7 to 4.8 s.

**What it rules out.** That the night rewards made them leave: thrust is pinned as hard by day as by night, in the parents as in the trained brains, so no night reward could have reached it. That unpinning thrust is the fix on this recipe: started over or pulled back, it ends below the edge, 0.3 to 0.8 outside and about 0 in the nest, and they stop foraging (0 to 6% alive against 42%) while still walking out of the nest. Moving costs nothing in this world (`[energy] move` 0, no effort pay), so slowing down saves no reward; a likely reading is that what speed is worth reaches the brain only through food some seconds later, a weak signal at gamma .99 on 0.2 s steps (about 20 s), so nothing pulls thrust back up once it's down.

**Limits.** The thrust check is one seed block of 64 games and the night brains only; that the tree and colony brains are pinned the same way is likely (same brain, same clip) but not measured. n50 is two runs of 2M with the learning rate the recipe anneals over 2M, not 8M; a longer run might relearn moving. The bound was tried at one weight (1.0), where it starts at about 5 against a policy loss near 0.01 and reaches every weight of the brain, not only the thrust output. Not tested: the bound on the thrust output alone or far weaker, a wider spread on thrust alone, or a longer horizon with thrust free.

**Replays and clips.** The channel's Nights line shows n50 and n51 with their questions (backups `lab/channel/live/`).

**Links.** 0017 (the nest is a pass-through); 0020, 0022 (the rewards that didn't move it); 0014; `../../ROADMAP.md`, 0.4.1.
