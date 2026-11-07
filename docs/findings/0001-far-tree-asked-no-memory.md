# 0001 The far tree asked for no memory

date: 2026-11-05 · status: held-out · seeds: held-out 32 per rung, held-out 64 · brains: the far-tree ladder (the 32 m rung's best seed; name not recorded), fs-parent, lam99 seeds

**Question.** The tree was pushed out to 32 m and called "out of sight". Did the brains need memory to bring apples home from it?

**World and brains.** The tree nursery from a brain choosing every 0.2 s, arena 8 → 32 m in 12 rungs of 8M samples, the nest's distance growing with the arena (trunk 2.8 → 11.2 m out). Later checks use the 32 m arena, sight 4 m, the trunk anywhere up to ±6 m from its usual spot, 90 s games.

**Method.** Each rung scored on 32 held-out games, apples home a minute, against the picker (sees every apple, wherever it is). Memory was tested by wiping the notes every 3 s. How much the tree is out of sight was measured afterwards with sight at 8 m. Later, two lam 0.99 seeds were compared with a script that remembers where it last saw the trunk (`tree_seen`) and a plain `searcher`.

**Result.** Apples home a minute:

| arena | 8 | 10 | 12 | 14 | 16 | 18 | 20 | 22 | 24 | 26 | 28 | 32 m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| picker | 15.6 | 13.1 | 11.4 | 10.1 | 9.0 | 8.0 | 7.3 | 6.7 | 6.1 | 5.8 | 5.3 | 4.7 |
| best seed | 15.4 | 13.8 | 12.2 | 10.7 | 9.4 | 8.4 | 7.6 | 7.1 | 6.6 | 6.1 | 5.7 | 4.9 |

Tree out of sight from the nest, sight 8 m: 0% of games at 16 m, 23% at 20, 66% at 24, 100% at 32. At 32 m the last brain brings home 4.9 a minute kept and 4.8 wiped every 3 s (4.875 against 4.8125, from the score files; the ladder's own log said 4.9 for both). With the tree at ±6 m and sight 4 m, lam 0.99 brought two seeds to 4.82 and 4.84 (parent 4.50, picker 4.93); wiping their notes every 3 s cost 0.01 and 0.17. In that world the brain's own search matched or beat the script that remembers. Where finding is hard enough for memory to matter, the scripts never reach home in about half the games (34 of 64 at ±12 m).

**What it rules out.** That 16 m was "out of sight": it wasn't, 0% of games. That the 32 m ladder shows memory: wiped scored the same as kept. The trunk also sits within 2.5 m of one spot every game and home is felt everywhere, so where the tree is can be learned into the weights with no notes. A far tree alone doesn't ask for memory; measure what a world hides before training in it.

**Limits.** One family of brains. 32 games a rung. The scorer then built each game without scattering the trunk, so far-tree scores were of a tree at its usual spot. Rescored with the fix (#115), every call in the ladder holds (the picker up 0.1–0.3 a minute, the best seed 0.0–0.2); the far tree at ±6 m drops below the picker (4.25 kept, 4.23 wiped, picker 4.83, 32 games). The table of wider spreads with sight 4 m (wiping cost 0–0.3) was not rescored and isn't used here. Seeds of the sight measurement: not recorded.

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "Moving things, and how far is far" and "A tree they go back to: what the notes hold"; #115; 0002 for what carried the way back instead.
