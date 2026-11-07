# 0004 The notes hold the tree's place and steer by it

date: 2026-11-06 · status: confirmed · seeds: 8,102,000 (swap), 8,103,000 (decode) · brains: mid2-s1, s2, s3 (one family, from lam99-s2)

**Question.** A wipe takes more than a place: the trip phase, the clock, a state the brain never trained on. Do the notes hold where the tree is, and does the brain steer by them?

**World and brains.** Rung A's world with the tree centred (nest in the middle of the garden, 32 m, ±12 m, `start` 1.5, `burrow`, trunk y 0). The layout check that refuses a trunk that near the nest was switched off; the nearest trunk left was 0.85 m from the nest, in games with the tree in sight from home, which are left out. The last checkpoints of `mid2`-s1, s2 and s3, frozen, no training.

**Method.** *The swap.* 2,048 games from seed 8,102,000; 1,799 qualify (249 have the tree in sight from home). At the first choice after the store goes up, the notes going in are the brain's own (intact), blank, those of a game whose tree lies at the same place (a median 12° and 0.6 m off) or the opposite way (168°). The first 512 recipients, matched to donors on emergence heading (0.2 rad) and time (0.2 s); the four conditions replay identically up to the swap (asserted). *The decode.* 3,000 games from seed 8,103,000, about 25,000 deposit samples a brain. A ridge regression (strength chosen by cross-validation grouped by game) reads the tree's offset from the notes at the first choice after a deposit, scored only where the trunk is not in sight. Gates set beforehand: for the swap, (a) above zero, (b) an interval clear of zero, (c) an interval holding zero or small; for the decode, median error under 2 m and 20° and under 0.8 of the best other read.

**Result.** The swap, paired 95% intervals:

| brain | (a) opposite less same: share of games setting off nearer the donor's tree than its own | (b) intact less blank: seconds to the next deposit | (c) intact less same-place: seconds to the next deposit |
|---|---|---|---|
| `mid2`-s1 | +0.28 [0.24, 0.32] | −5.0 [−5.8, −4.2] | −0.41 [−0.92, 0.10] |
| `mid2`-s2 | +0.34 [0.30, 0.38] | −7.8 [−8.9, −6.8] | −0.82 [−1.44, −0.18] |
| `mid2`-s3 | +0.15 [0.10, 0.19] | −4.1 [−4.8, −3.3] | −0.10 [−0.54, 0.33] |

All pass but one: (c) for s2 is a small miss (0.8 s, a tenth of the blank effect). Mean seconds to the next deposit (45 s cap), intact / blank / same-place / opposite: s1 19.5 / 24.5 / 19.9 / 27.2; s2 21.6 / 29.5 / 22.4 / 32.7; s3 17.3 / 21.4 / 17.4 / 23.6. The decode, median error in metres / degrees of bearing:

| brain | split | notes | senses + notes | senses only | nuisance only | notes shuffled |
|---|---|---|---|---|---|---|
| s1 | game | 1.24 / 8.5 | 1.22 / 8.5 | 6.6 / 69 | 6.5 / 69 | 6.6 / 69 |
| s1 | sector | 1.78 / 12.5 | 1.77 / 12.4 | 8.7 / 134 | 8.8 / 137 | 8.5 / 136 |
| s2 | game | 0.98 / 6.3 | 0.95 / 6.2 | 5.0 / 47 | 6.1 / 62 | 6.4 / 63 |
| s2 | sector | 1.47 / 10.1 | 1.43 / 10.0 | 7.3 / 100 | 8.3 / 122 | 8.1 / 121 |
| s3 | game | 1.24 / 7.5 | 1.21 / 7.5 | 7.0 / 68 | 6.9 / 68 | 7.0 / 73 |
| s3 | sector | 1.77 / 11.7 | 1.75 / 11.6 | 8.9 / 139 | 9.1 / 141 | 8.8 / 145 |

**What it rules out.** That a wipe only breaks the brain's state: same-place notes from another game do as well as its own (within 0.1–0.8 s), so a blank note costs the information. Wrong notes cost more than none (opposite 27.2 against blank 24.5 s in s1, 32.7 against 29.5 in s2, 23.6 against 21.4 in s3). That the place is readable from the current senses or from state that could stand in for place: both read 5–9 m out. The twin-training control a review proposed (48M samples) isn't needed to answer the shock question.

**Limits.** The heading at 3 m is loose even intact (median 65–74° off), so the trip time, not the set-off direction, carries the effect. Only heading and time were matched; crop, energy and store happened to be equal at the swap point. On s2 the senses-only read gets down to 5.0 m, perhaps from seeing apples as food, unchecked. 30–35% of decode samples come from games with the tree in sight from home. The reads are linear, so a failed one would not have proved the notes empty. First deposit only in the swap; one world, three brains of one family. The thresholds are ours, set before the run. Trees more than 6 m from the nest decode to 1.3–2.2 m and 6–9.5°; in the body's frame the error is about 7 m everywhere, which a linear read can't undo.

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("The matched swaps and the decode probe"); #115; 0003 before, 0005 and 0011 after.
