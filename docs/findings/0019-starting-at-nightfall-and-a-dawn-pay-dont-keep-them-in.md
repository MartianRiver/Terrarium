# 0019 Starting games at nightfall and a pay at dawn for being home don't keep the night brains in

date: 2026-11-08 · status: held-out · seeds: 2,000,000 × 256 (scores), 8,112,000 × 256 (leave battery) · brains: n47-dark-s1, -s2; n47-dawn-s1, -s2 (last checkpoints, 8.0M samples each on n43-nm-s1 and -s2); controls n45-nm3-s1, -s1b, -s2, -s2b

**Question.** The night brains walk straight back out of the nest in the dark, fed or hungry (0017), and more training or a pay for warmth didn't change it (0018). Do they learn to stay in if half their training games start at nightfall with them at home, so staying in is practised from the first tick, or if each nim in its own nest when the night ends is paid once, as much as dying costs?

**World and brains.** The night world of 0014 to 0018: one colony of two, the apple tree with burrow, a 60 s night in each 120 s cycle, dusk 10 s, drain 0.0125 a second, 128 note slots. Both forks are 8M samples from n43-nm-s1 and -s2 on 0.4's recipe with `[reward] needs` 1.0, one change each: n47-dark trains in the world with `[night] start_dark` 0.5 (half the games start at the first full dark, the nims in the nest, no food standing); n47-dawn trains with `[reward] dawn` 1.0. The control is n45-nm3, the same parents and 8M of the same recipe without the change, two runs a parent.

**Method.** `mates.py` on 256 games from seed 2,000,000, the same games for every brain, at 300 s (two nights) and 180 s (one night), in the standard night world (`start_dark` 0, so the dark-start brains are tested as the others are). Alive is the share of nims alive at the end, notes wiped for both nestmates whenever either stores (the "both" row). Then 0017's battery, its clock start: both nims in the nest at the first full dark, 256 games from block 8,112,000, four starts (F fed with jelly stored, H hungry with jelly, E fed with no store, HE hungry with no store), played 60 s to dawn.

**Result.** Alive at the end, both row:

| brains | change | 300 s | 180 s |
|---|---|---|---|
| n45-nm3 s1, s1b / s2, s2b | control | 36, 39 / 51, 43 (42) | 49, 53 / 69, 56 (57) |
| n47-dawn s1 / s2 | pay at dawn for being home | 40 / 40 (40) | 53 / 62 (57.5) |
| n47-dark s1 / s2 | half the games start at nightfall | 27 / 44 (35.5) | 47 / 67 (57) |

In the battery the dawn brains leave the nest as their parents did (0017): 511 or 512 of 512 nims in every start, a median 1.4 s after the dark start, and n47-dawn-s2 keeps 91% alive at dawn from the fed start, n43-nm-s2's number. n47-dark-s2 leaves the same way (512 of 512 in every start, 1.25 to 1.35 s). n47-dark-s1 is the one exception: with the store empty only 389 (E) and 309 (HE) of 512 leave, and 32% are alive at dawn in E against 5 to 16% for the others, but with jelly stored it leaves 512 of 512, and in whole games it is the worst of the four (27% over two nights).

**What it rules out.** That practising the night from home, or a pay at the night's end, gets these brains to stay in at night within 8M: neither lifts the share alive, and neither changes the walk-out. The dawn pay left no trace in behaviour at all, so it was not learned, rather than learned and wrong: a pay that comes once, a whole night after the choice to leave, may be too far off for this brain to tie to the choice.

**Limits.** Held-out seeds only, one block, 256 games a cell, two runs a change, so a change of a few points is inside the noise between twins (up to 10 points, 0018). One dawn value (1.0, as big as dying costs) and one share of dark starts (0.5); both from the n43-nm line. n47-dark-s1's partial staying-in with an empty store is one seed and didn't show in its twin.

**Replays and clips.** The channel's Nights line shows both questions with their runs (backups `lab/channel/live/`).

**Links.** 0017 (they walk back out of the nest); 0018 (more training, two-night games, warmth and cold don't help); 0014 (the needs reward); `../../ROADMAP.md`, 0.4.1.
