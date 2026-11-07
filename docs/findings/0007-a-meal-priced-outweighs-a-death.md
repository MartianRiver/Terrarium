# 0007 A cost at the moment of eating outweighs a death 40 s off

date: 2026-11-06 · status: confirmed · seeds: 2,000,000 (forks), 8,106,000 (confirm) · brains: grown-s1, s2, s3 and their meals-free forks (one family, from duo2)

**Question.** In a world with grown-up costs, two of three seeds traded their lives for deliveries, and more training made it worse. Why, and does a price on eating explain it?

**World and brains.** Rung D (two to a nest) with the drain of rung E, so one that never eats starves at 80 s, and grown-up rules (`[young] start` false): eating takes a whole jelly for 0.4 energy and only below 0.6, and each jump costs 0.01 energy. `grown`-s1/s2/s3: 8M each from the duo brains. Guess under test: eating costs `[reward] jelly` −0.5 at once, while dying (−1) comes 40 s later, about −0.13 after discounting (gamma 0.99 at 5 choices a second).

**Method.** Three forks from grown-s1, one change each, 8M, scored on the same 256 games (seed 2,000,000). Then the meals-free fork on the other two seeds, all three confirmed on 256 fresh games from seed 8,106,000. Picker 7.85 (it never eats), searcher 1.89, tree in sight 2.14 on the confirm games.

**Result.** Forks of s1, apples a minute per nest:

| fork | apples a minute per nest | alive at the end | jellies eaten each | own notes |
|---|---|---|---|---|
| grown-s1 (parent) | 8.61 | 77% | 1.25 | +1.05 |
| grown2-s1 (8M more, no change) | 8.15 | 40% | 0.61 | |
| eating free (`[reward] jelly` −0.5 → 0) | 9.52 | 97% | 1.93 | +0.80 [+0.60, +1.00] |
| dearer death (`death` −1 → −3) | 9.17 | 83% | 1.40 | +1.31 [+1.05, +1.60] |
| 180 s games | 7.42 | 42% | 0.61 | +0.62 [+0.44, +0.81] |

The 180 s fork scored 5.13 a minute with 11% alive at 180 s, against grown-s1 at 7.51 and 44%. Confirmed on 8,106,000, parent → meals free:

| brain | apples a minute per nest | alive at the end | own notes | nestmate's notes |
|---|---|---|---|---|
| s1 | 8.65 → 9.53 | 77 → 96% | +0.70 [+0.52, +0.87] | +0.27 [+0.09, +0.43] |
| s2 | 7.42 → 7.80 | 89 → 92% | +0.81 [+0.53, +1.08] | +0.10 [−0.07, +0.28] |
| s3 | 7.46 → 8.55 | 60 → 90% | +0.81 [+0.62, +1.02] | −0.00 [−0.13, +0.12] |

**What it rules out.** That the game's length is the reason: longer games starve them partway through too. A dearer death helps a little. With a meal free all three live, bring home as much as their parents or more (0.99–1.21 of the picker) and keep their own memory. The nestmate's notes show for s1 (+0.27), a hint only.

**Limits.** The cause (the −0.5 cost against a far death) was tested as forks of one seed, one run each. s2 lives differently, eating apples where it picks them (most of its energy from food, 0.3 jelly a game) where s1 and s3 eat from the store. With eating free, nothing in this world makes a meal cost the colony, as the store isn't spent on anything else; in the colony world the store hatches eggs, so a price will be needed there. In the fork table s2's parent started from a different place (duo2-s2, untrained in this world) from s1's (drain-s1).

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("Rung E2: grown-up costs", "Pricing a meal"); 0006 before, 0010 after.
