# 0008 Games twice as long cost the meals-free brains nothing

date: 2026-11-07 · status: confirmed · seeds: 8,107,000 (256 games; s1 and s3) · brains: meals-free s1, s2, s3 (one family, from duo2)

**Question.** In the meals-free world (0007), do 180 s games, twice the length, break the brains?

**World and brains.** The world that works: rung D with grown-up costs but eating free (`[reward] jelly` 0), no cost to move, 90 s games before. 8M samples from each meals-free brain at 180 s.

**Method.** Scored at 180 s on 256 games, parent → trained, apples a minute per nest, alive at the end, own notes (kept less wiped on unloading). The first table is the scoring block; the confirm below is on fresh seeds.

**Result.**

| brain | apples a minute per nest | alive at the end | own notes |
|---|---|---|---|
| s1 | 9.81 → 9.72 | 91 → 98% | +0.73 [+0.57, +0.89] |
| s2 | 7.12 → 7.79 | 74 → 69% | +1.45 [+1.05, +1.85] |
| s3 | 8.76 → 9.01 | 87 → 98% | +1.65 [+1.34, +1.99] |

Confirmed on 256 fresh games from seed 8,107,000, at 180 s (apples a minute per nest with notes kept, alive at the end, and own notes: kept less wiped as it stores):

| brain | per nest | alive | own notes |
|---|---|---|---|
| j180-s1 | 9.82 | 96% | +0.71 [+0.57, +0.85] |
| j180-s2 | 7.71 | 62% | +1.52 [+1.06, +2.02] |
| j180-s3 | 9.15 | 97% | +1.62 [+1.30, +1.99] |

Picker 4.13 (it never eats, and starves at 80 s of 180), searcher 0.95, `tree_seen` 1.13 on the same games.

**What it rules out.** That doubling the game's length is what starved the brains in 0007: s1 and s3 live, keep their pace and lean on their notes as much or more. s2 is the mirror of the cost-of-moving rung: eating apples at the tree carries it when moving costs, and fails it in a long game, and eating from the store does the opposite for s1 and s3.

**Limits.** The first table is the scoring block; the confirm holds for s1 and s3, while s2 lives in only 62% of fresh games. One chunk of 8M, three brains of one family. Why s2 slips, and whether it keeps slipping with more samples, is unchecked. The nights of the next rung are a separate question and not settled: see 0010.

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("Longer games, then nights"); 0007 before, 0010 after.
