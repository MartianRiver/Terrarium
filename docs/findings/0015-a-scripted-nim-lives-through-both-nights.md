# 0015 A scripted nim lives through both nights; the brains die out in the dark, not by deadlock

date: 2026-11-07 · status: confirmed · seeds: 2,000,000 × 256 (script and brains), 8,110,000 × 256 (script, fresh), 8,111,000 × 256 (brains at 300 s, fresh) · brains: n42-gn-s2, n43-nm-s2, n43-nm-s1 (last checkpoints, 8.0M samples each on their parents)

**Question.** The 0.4.1 gate asks 85% of nims alive through two nights. Is the world's food too thin for that, and what kills the best brains: nestmates blocking each other, or something else?

**World and brains.** The night world of 0012 and 0014 (one colony of two, apple tree with burrow, a 60 s night in each 120 s cycle, dusk 10 s, cold 0.005, drain 0.0125 a second), played at 180 s and at 300 s, which is two nights: a 180 s game holds one night, its second dusk falls at 170 s and the dark at 180 s. The three brains are the best of 0014 (53.7, 69.5 and 53.7% alive at 180 s, notes wiped for both). The scripts are instruments, never carried forward: `script:0:0.3` goes home when the dark falls, eats when its energy is under 0.3 and otherwise takes the nearest apple; `:split` adds that the second nim takes the nearest apple the first is not nearest to.

**Method.** The scripts on 256 games of seed 2,000,000 (the games 0014 scored on) and of fresh block 8,110,000, at 180 and 300 s. The brains on seed 2,000,000 at 300 s, played as in `mates.py` (notes wiped for both whenever either stores; the notes-kept row alongside), alive at 180 s read from the same games. Every death is classed by time, phase, light, distance from the nest's middle, store and crop, whether the nim had been inside that night, and a wedge rule: the two nestmates within 1.1 m, both within 0.8 m of the same standing apple, both slower than 0.15 m/s and asking for thrust; a death is a deadlock if its nim spent over 20 s wedged and stored 0 or 1 apples. Scripts and per-game outputs are in the lab folder, outside the repo.

**Result.** Alive (share of nims) and how the deaths fall, seed 2,000,000:

| | alive 180 s | alive 300 s | 300 s, notes kept | deaths (of 512) | in the dark, away from the nest | deadlock by the wedge rule | pair wedged, s a game |
|---|---|---|---|---|---|---|---|
| script, unsplit | 97.7% | 97.5% | | 13 | 0 | 9 | 6.7 |
| script, split | 99.4% | 99.4% | | 3 | 0 | 3 | 2.5 |
| n42-gn-s2 | 53.7% | 39.6% | 60.7% | 309 | 300 (97%) | 0 | 0.0 |
| n43-nm-s2 | 69.5% | 50.0% | 57.0% | 256 | 232 (91%) | 0 | 0.0 |
| n43-nm-s1 | 53.7% | 41.6% | 46.5% | 299 | 290 (97%) | 0 | 0.0 |

The split script is 100.0% alive at 180 and at 300 s on the fresh block; the unsplit one 96.9% at 180 s there. The script's deaths are all at about 77 s, in the dark, within 1 m of the nest with the store empty and nothing carried: two nestmates take the same nearest apple from opposite sides, their centres 0.89 m apart and each 0.4 to 0.5 m from it (a jump needs under 0.3 m), and both push until they starve. By the wedge rule that is 9 of the unsplit script's 13 deaths and 3 of 3 with the split; the other 4 died at the nest with the store empty, three of them having never fed while their mate stood stuck at an apple for 13 to 54 s (not traced further). The food is enough: a nim needs 0.0125 energy a second, 1.5 a 120 s cycle, and an apple gives 0.4, so about 7.5 apples a cycle for two and 8.5 to 9 with the jumps; the script brings in 9.6 a day and the store grows (14 to 16 at 180 s, 22 at 300 s). Time spent foraging is paid for in the store: lead 0, 10 and 20 s before the dark leaves 9.1, 7.0 and 5.4 apples at the first dusk and 97.5, 93.8 and 91.0% alive at 300 s.

On the fresh block 8,111,000 the brains' share alive at 300 s holds: 39%, 51% and 40% (notes kept 58%, 52%, 43%), against 39.6%, 50.0% and 41.6% on the held-out games.

The brains never deadlock: 0 of 864 deaths at 300 s (none either with the notes kept, or at 180 s), and the pair is wedged 0.0 s a game on average (some wedge in 1 to 4% of games, and recover). They die out in the dark: 91 to 97% of the deaths, a median 6.4 to 7.1 m from the nest, at a median 95 to 118 s, mid-night (75%, 57% and 78% of each brain's deaths fall in the first night). At dusk, 60 to 70 s, 0 to 7% of the living are in the nest, a median 4.8 to 6.1 m out, still walking at 1.9 m/s; the script has 86% inside at 65 s and all by 70 s. Of the dark deaths 73, 34 and 39% still had jelly in the store, and 44, 70 and 49% had been inside that night and left again. The store at 60 s is 6.3, 6.3 and 5.2, the script's 9.1 (10.1 split). From the nims alive at 180 s, 72 to 78% are alive at 300 s.

**What it rules out.** That the world's food is what holds the brains below 85%: a scripted nim in this world, same food, is 99.4% alive on the gate games and 100% on a fresh block, at both lengths. That nestmates blocking each other kills the brains: no deadlock death in 864, and no wedging in living pairs. What is left is the night return: they are out at dusk, a store of 5 to 6 against the script's 9 to 10, and 44 to 70% of the dark deaths had left the nest again that night.

**Limits.** The shares alive are confirmed on fresh blocks (the script on 8,110,000, the brains at 300 s on 8,111,000), but the death classes and the wedge counts come from the held-out games only, three brains from one family with one run each. The script's 100% is on a fresh block, and the script is an instrument: it reads the dark where a brain reads a light. `mates.py` draws action noise a stream a nim, the score job a stream a game, so the brains' numbers here will differ a little from a score job's. The headroom scripts ran in `nightq/world.toml`, the brains in the 0014 world, which differs by `[home] compass = true`, the setting the old file always played. The wedge rule and the death classes are the worker's own, thresholds chosen once (1.1 m, 0.8 m, 0.15 m/s, 20 s); the kept row is a second look at the same games, not an independent one. A 180 s game holds one night, so every 180 s number in 0012 and 0014 reads one night, not the gate's.

**Replays and clips.** None kept.

**Links.** 0014 (the brains and how they got here); 0012 (the first night battery); `../../ROADMAP.md`, 0.4.1.
