# 0010 Nothing paid for a meal in the night forks

date: 2026-11-07 · status: open · seeds: not applicable (a reading of existing runs) · brains: meals-free s1, s2, s3 and their night forks (one family)

**Question.** In the colony world's nights the food standing goes and the store is all there is. The brains starve at night with jelly at home. Do they refuse to go home to eat, or was going home to eat never paid for?

**World and brains.** The meals-free world (0007) on the 180 s game with the colony's nights (a day and night every 120 s, the last 60 dark). 8M and 16M samples from the meals-free brains.

**Method.** Alive at the end, parent → 8M → 16M, at a quarter of the colony's cold (0.02 a second, kept off in the nest). Parents at the colony's full cold ended 0–2% alive and 8M left them at 0–9%.

**Result.**

| brain | quarter cold, alive at the end: parent → 8M → 16M | apples a minute per nest at 16M | own notes at 16M |
|---|---|---|---|
| s1 | 7 → 32 → 38% | 4.06 | +0.31 [+0.13, +0.49] |
| s2 | 6 → 44 → 67% | 5.49 | +0.53 [+0.38, +0.69] |
| s3 | 2 → 0 → 2% | 2.79 | +0.19 [+0.13, +0.25] |

**What's known.** At the colony's cold the parents die in the first half of the first night with 5–6 jelly in the store; at a quarter of the cold the parents die just the same (2–7%), so it isn't the cold. At night there is nothing to bring home, so they stay out and starve. The notes are worth less with nights (+0.2–0.5, against +0.7–1.7 without). The runs trained with `food`, `needs` and `jelly` all 0 (the tree's points pay on unloading), so the only thing a meal was worth was putting off death's −1, which a gamma of 0.99 at 5 choices a second halves every ~14 s. A meal from the store also pays nothing in `food` or `needs` even when they're on: the reward counts a meal through `fed`, and eating from the store adds to energy and jelly but never to `fed` (a known bug). Before this, the paying-to-move rung (half the cost) had s1 and s3 dying with a nearly empty store, and s2 clearing it by eating apples at the tree.

**What isn't known.** Whether paying for a meal brings them home when hungry. "They've only ever gone home to deliver" is still a guess: these runs never asked. "Going home to eat is a skill of its own, s2 is learning it, s3 hasn't started" is a reading, not a test.

**Next test.** Fix the meal count (`fed` for eating from the store), then test with weights frozen first, then a fork, one change from the meals-free world.

**Limits.** 256 games on the scoring block only; three brains of one family; the death times from 128 games. The bug is not fixed in the runs above, and its exact effect on the totals is unmeasured.

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("Rung F: paying to move", "Longer games, then nights"); 0007, 0008, 0009.
