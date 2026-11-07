# 0005 It goes where it remembers, and stale memory costs

date: 2026-11-06 · status: confirmed · seeds: 8,104,000 · brains: mid2-s1, s2, s3 (one family, from lam99-s2)

**Question.** If the tree moves while a nim is down in the burrow, and its notes hold the old place, does it walk back to an empty spot?

**World and brains.** Rung A's world, tree centred (as in 0004). While the nim is down storing an apple, the tree moves at least 6 m, somewhere it can't be seen from home. The last checkpoints of `mid2`-s1, s2 and s3, frozen.

**Method.** 512 games each from seed 8,104,000; 57 games have the tree in sight from home and never move, and are left out. Three ways to play each game: the tree stays, the tree moves, the tree moves and the notes are wiped as it stores. "To the old spot" means within 1.5 m of where the tree was, before it sees the new tree.

**Result.**

| brain | first trip to the old spot, moved | moved + wiped | difference | next deposit, still / moved / wiped | apples a minute, still / moved / wiped |
|---|---|---|---|---|---|
| s1 | 32% | 14% | +18 [+14, +23] | 19.4 / 27.4 / 23.4 s | 4.10 / 1.73 / 2.07 |
| s2 | 39% | 20% | +19 [+15, +23] | 22.2 / 29.8 / 29.1 s | 3.88 / 1.55 / 1.53 |
| s3 | 36% | 18% | +17 [+13, +22] | 17.4 / 25.1 / 21.1 s | 4.32 / 2.32 / 2.73 |

Later trips after a move: s1 +11 points and s2 +19 hold, s3 +2 [−0.4, +5] doesn't. Once the tree has moved, the heading to the new place is 78–88° off for all three: it goes where it remembers and then has to search like anyone else. The replays show it (s2 game 488: within 0.2 m of the old spot, stays near it 11–15 s, finds the new tree at 20.7 s).

**What it rules out.** That the notes only help with something other than place: twice as many first trips end at the empty old spot kept as wiped, three brains out of three. It also shows what remembering costs: about 4 s a trip on s1 and s3 when the world changes under it, so a moved tree is worse with notes than without. Nothing in the world has asked a brain to notice a place is empty and update.

**Limits.** A still game is no baseline for "went to the old spot" (the tree is there). 30–56% of later trips are cut off by the game's end and aren't matched. The wiped games still reach the old spot 14–20% of the time, perhaps by chance on the way out, unexplained. One world, three brains of one family. Earlier, a coarser test in rung B (the tree moves once at half time, totals and time to the first apple after the move) could not settle this: the headline "memory pays half as much after the move" was withdrawn because the kept and wiped trips came from different games (71% against 57% of games reach one) and 12.7 s counted only searches that succeeded (19.5 s with failures at the 45 s cap).

**Replays and clips.** Replays of s2 game 488 and others were looked at; paths not recorded.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("Moving the tree"; "Rung B: the tree moves once"); 0004 before.
