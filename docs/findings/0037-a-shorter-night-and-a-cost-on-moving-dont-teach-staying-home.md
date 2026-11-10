# 0037 A shorter night and a cost on moving don't teach the night brains to stay home; a fed nim out all night dies only at the end of the night, but the brains as they play die within 10 to 50 s of dark

date: 2026-11-10 · status: held-out · seeds: 2,000,000 × 256 (n55 in the 60 s night and in its own 30 s night, the held-out block, also used for choosing); 9,970,000 × 256 (n55, n57 and the control, both worlds, fresh, never used for choosing); 9,980,000 × 128 (death times for n58-ctl and n58-cold06, fresh); night check seed 1,000,000 (scripted nims, 64 arenas, 3 nights); training seeds 661 and 662 · brains: n52-ctl-s1 and -s2 (the 8M controls of 0035, also the parents), n55-short30-s1 and -s2 (n52-ctl + 8M in a 30 s night), n57-work-s1 and -s2 (n55's world + a cost on moving, body branch e485d5e), all 8M samples; n56-day240 is void and not read

**Question.** The night brains (0017, 0035, 0036) walk out of the nest at night and die. Two cheap ways to change what the world pays for that: a shorter night (n55: easier to be out in, so more of the training game is night worth practising) and a cost on moving fast (n57: `[energy] work` 0.005, so the thrust pinned at full, 0024, costs something). Does either teach them to stay home?

**World and brains.** The night world of 0035 (one colony of two, apple tree with burrow, 120 s cycle, 60 s night, cold .005, drain .0125, `needs` 1.0, gamma .99, training games 180 s) with one change each, from n52-ctl, 8M, seeds 661 and 662:
- n55: night 30 s of the 120 s (`world-short30.toml`), nothing else. It sees a night in every game (dark from 90 s).
- n57: n55's world plus `[energy] work` 0.005 (moving costs by weight and the share of top speed, the body branch at e485d5e). n55 is its matched control.
- n56 (240 s cycle, 40 s night) is **void**. In its world dusk falls at 190 s and dark at 200 s, but the training games are 180 s, so n56 trained with no night at all (Codex, 10 Nov; its test 3 counted zero night samples at 180 s, dawn slots 0, in 0036). It was scored, and its numbers are kept out of the result.

**Method.** Scores with `mates.py` (as 0035), 256 games × 300 s, the same games for every brain in a block: n55 on 2,000,000 in the 60 s night and in its own 30 s night (with the n52-ctl parents), and n52-ctl, n55 and n57 on 9,970,000, scored once, in the 60 s night and in the 30 s night with the work cost. "Kept", "self" and "both" as in 0035. The night check (`terrarium.nightcheck`, scripted nims, 64 arenas × 3 nights, seed 1,000,000, energy held full by day so that only the night can kill): the nim stays home and rests (home), stays still out (out-still), walks all night (out-wander), huddles out, or walks out until mid-night and then goes home (late-home), in the 60 s night at cold .005, the 30 s night at cold .005, and the 60 s night at cold .02. Without the held-full energy every scripted nim starves by day at drain .0125, so that run says nothing about the night.

**Result.** Alive at the end of 300 s, kept / self / both, and nest kept (apples home a minute), seeds as s1 / s2. In the 60 s night, the world they are meant to stay home in:

| brain | block | alive, kept | alive, self | alive, both | nest, kept |
|---|---|---|---|---|---|
| n52-ctl | 2,000,000 | 47 / 58% | 47 / 50% | 43 / 50% | 4.73 / 5.07 |
| n55 | 2,000,000 | 46 / 52% | 36 / 43% | 36 / 46% | 4.59 / 4.79 |
| n52-ctl | 9,970,000 | 45 / 55% | 44 / 46% | 38 / 47% | 4.82 / 5.28 |
| n55 | 9,970,000 | 44 / 48% | 38 / 45% | 36 / 41% | 4.77 / 4.91 |
| n57 | 9,970,000 | 44 / 47% | 38 / 42% | 33 / 36% | 4.93 / 4.98 |

In their own worlds:

| brain | world, block | alive, kept | alive, self | alive, both | nest, kept |
|---|---|---|---|---|---|
| n52-ctl | 30 s night, 2,000,000 | 80 / 80% | 69 / 80% | 65 / 73% | 7.23 / 7.34 |
| n55 | 30 s night, 2,000,000 | 80 / 88% | 71 / 78% | 67 / 72% | 7.23 / 7.85 |
| n52-ctl | 30 s night + work, 9,970,000 | 52 / 67% | 50 / 59% | 46 / 56% | 6.73 / 7.26 |
| n55 | 30 s night + work, 9,970,000 | 54 / 60% | 48 / 59% | 44 / 55% | 6.73 / 7.26 |
| n57 | 30 s night + work, 9,970,000 | 54 / 61% | 46 / 51% | 41 / 43% | 7.00 / 7.31 |

n55 does not beat the control in the 60 s night on either block: 1 to 11 points under it in every cell on 2,000,000, and 1 to 7 under in every cell on 9,970,000 (kept 1 and 7, self 5 and 2, both 2 and 6). In its own 30 s night it is level with the control except s2's kept row (+8; self +2 and -2, both +2 and -1, kept s1 level); the jump from about half alive to about 80% is the shorter night being easier for the control too, not learning. n57 against n55, its matched control: in the 60 s night kept level (44 / 44, 47 / 48), self 0 and 3 under, both 4 and 5 under; in the 30 s night with work kept level (54 / 54, 61 / 60), self 2 and 7 under, both 3 and 12 under. Its nest rate is a little up (+0.27 and +0.05 with work, +0.16 and +0.07 in the 60 s night) and its survival is not.

The night check, fed scripted nims, share alive at the end of three nights:

| world | home | out-still | out-wander | huddle-out | late-home |
|---|---|---|---|---|---|
| 60 s night, cold .005 | 100% | 0% | 0% | 100% | 100% |
| 30 s night, cold .005 | 100% | 100% | 100% | 100% | 100% |
| 60 s night, cold .02 | 100% | 0% | 0% | 0% | 0% |

At cold .005 in the 60 s night, a fed nim out all night dies of cold; 5% of out-still reach the first dawn at chill 0.48 against the 0.5 that kills, so a death falls at the end of the night (the tables give no per-nim death time). A death 57 s into the night, as the arithmetic below takes it, is worth e^(-57/19.9), about .06, to a brain whose gamma .99 at 0.2 s decisions gives an e-folding of about 19.9 s. In the 30 s night, out all night lives, at a chill of .82 at dawn. At cold .02 out and late-home both die.

**What it rules out.** That a shorter night teaches them to stay home (n55: no lift on two seeds on either block, and a drop in the 60 s night on the fresh one). That a cost on moving does (n57: no lift against its matched control, and its both rows are worse). Not why. The scripted check suggested one: in the 30 s night a fed nim out all night lives, and in the 60 s night it dies only at the end, which a brain weighing about 20 s ahead sees at about .06. The brains as they play don't match it. Death times for n58-ctl and n58-cold06 (n52-ctl + 8M, 9,980,000 × 128, 300 s, notes kept, in 10 s bins) put the deaths 10 to 50 s into each night (bins 70, 90 and 110 s in the first, 190 to 240 s in the second), about half in the first, a median 7 to 8 m from their nest, 0 to 6% inside it, in the dark; they come to nightfall at energy .67 to .68 on average, 41 to 66% under .6, not fed. So being out kills well inside the brain's reach in the control's own world, and the reach alone doesn't explain why they go (0036's dusk trade is the stronger lead: the last apple now against a death that costs only −1, about a seventh of what a game returns). The cold-.02 row still says a harsher night kills even a nim that goes home late.

**Limits.** `held-out`, not `confirmed`: the fresh 9,970,000 block carries the no-lift calls for n55 and for n57 (a first and only read for n57, two seeds, scored once), and the 2,000,000 block is the held-out one used for choosing and agrees for n55; and it settles no why: the scripted check's reach argument fits fed nims only (above). The scripted nims are not the brains: fed, still or walking, and a brain that is hungry or carries food may die sooner. The death time comes from the chill at dawn of the few out-still survivors, not a per-nim time, so .06 is an estimate. One work weight (0.005, which Codex's reading of the code puts at about .001 of reward a 0.2 s decision at hunger .5, against a delivered apple worth 1), one shortened night (30 s), two seeds each, 8M each. n57 was scored with the body branch as it was trained (before its fixes). Baselines read lower on the fresh block than on 2,000,000 (0035), so numbers compare only within a block.

**Replays and clips.** None.

**Links.** 0017 (the pass-through nest); 0018, 0019 (more pays and dawn pays); 0022 (charging for the cold); 0024 (the pinned thrust); 0035 (the spread reset and the dusk probe); 0036 (hold and release, and what going home costs). Next step: a harsher cold (n58, n60), a costlier death (n61) and a longer reach (n59), each against a matched control, in their own findings.
