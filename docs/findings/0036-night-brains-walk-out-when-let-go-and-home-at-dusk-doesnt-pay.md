# 0036 A night brain walks out of the nest within about a second of being let go, even after 20 s held in it, and going home at dusk lifts dawn survival 18 points but costs the last apple before nightfall, so the return it trains on doesn't pay for it

date: 2026-11-10 · status: confirmed · seeds: 9,910,000 (dusk intervention, 64 games × 4 action draws), 9,920,000 (hold and release, 64 games), 9,930,000 to 9,934,000 in steps of 1,000 (value by phase, 5 × 64 games); none used for choosing · brains: n52-ctl-s1 and -s2 (n49 + 8M, the control of 0035), 8M samples; n55-short30-s1 and -s2 for the value read only

**Question.** The night brains (0017, 0035) leave the nest within about a second at night. Is that because staying is never sampled, because the reward for going home is too small inside their horizon, or because the value function misjudges the night (a review by Codex, 10 Nov, three tests)?

**World and brains.** The night world of 0035: one colony of two, apple tree with burrow, 60 s night in each 120 s cycle, `needs` 1.0 and `needs_lost` 1.0, gamma .99, colony blend .5, training games 180 s. The brains are the 8M controls n52-ctl-s1 and -s2.

**Method.** Scripts `test1_paired_blend.py`, `test2_hold_release.py`, `test3_dawn_value.py` (Codex's three tests, built by a worker; kept in the lab folder `2026-11-10-codex-tests` with every output, Codex's report is `2026-11-10-codex-night2/report.md`). (1) Dusk at 56 s of the cycle, nim 0 outside the nest in 53 of 64 games (s1) and 56 (s2): the brain as it is against steered straight home for 20 s then released, same games and noise, discounted return over 20 and 60 s (with and without the critic's value at the end), alive at dawn, and apples stored by that nim from dusk to dawn; once with the colony blend at 0 (own reward) and once at .5. (2) From its first arrival home in the dark (50 to 61 of 64 games), nim 0 is held still (thrust and turn 0) for 0, 5 or 20 s, then released; notes run throughout. (3) The normal collector on 64 arenas for one 180 s episode, five seed blocks: how many nims are alive and in their own nest at dawn (where the dawn pay would land), and the value's explained variance and bias against the sampled discounted return in four phases.

**Result.** Going home at dusk, home minus brain, mean ± SE over games (return = discounted, 20 s; "+v" adds the critic's value at 20 s):

| brain | blend | return 20 s | return 60 s | return 20 s +v | alive at dawn |
|---|---|---|---|---|---|
| s1 | 0 (own) | -0.046 ± 0.042 | -0.041 ± 0.046 | -0.118 ± 0.058 | +0.179 ± 0.054 |
| s1 | .5 | -0.076 ± 0.043 | -0.080 ± 0.046 | -0.148 ± 0.058 | +0.179 ± 0.054 |
| s2 | 0 (own) | -0.030 ± 0.047 | -0.026 ± 0.051 | -0.046 ± 0.046 | +0.183 ± 0.051 |
| s2 | .5 | -0.070 ± 0.044 | -0.071 ± 0.048 | -0.087 ± 0.043 | +0.183 ± 0.051 |

Held at home and released (shares of nims at home and alive at the release):

| brain | hold | at home at release | still home 10 s on | median s to leave | alive at dawn vs no hold |
|---|---|---|---|---|---|
| s1 | 0 | 61 | 0 of 61 | 0.8 | - |
| s1 | 5 s | 45 | 0 of 45 | 1.0 | +0.016 ± 0.016 |
| s1 | 20 s | 21 | 0 of 21 | 1.2 | +0.164 ± 0.058 |
| s2 | 0 | 50 | 0 of 50 | 0.8 | - |
| s2 | 5 s | 43 | 0 of 43 | 0.8 | -0.080 ± 0.048 |
| s2 | 20 s | 8 | 0 of 8 | 0.9 | +0.020 ± 0.020 |

Apples the same nim stores between dusk and dawn (mean over the paired games, home minus brain; the colony blend doesn't touch it):

| brain | brain's own way | steered home | home minus brain |
|---|---|---|---|
| s1 | 0.63 | 0.49 | -0.146 ± 0.072 |
| s2 | 0.78 | 0.37 | -0.406 ± 0.077 |

With the brain's mean action instead of sampled actions the same: 0 of 58, 45, 20 (s1) and 54, 44, 11 (s2) stay 10 s.

Value against return, explained variance (bias value minus return), pooled over 5 blocks, s1 / s2: day .83 (-.05) / .83 (+.07); 10 s before dark .59 (+.12) / .63 (+.19); night .74 (.00) / .77 (-.01); next day .83 / .85. Alive and in their own nest at dawn: 50 of 437 living nims (11%) s1, 22 of 469 (5%) s2. n55 (30 s nights, its own world): 10.5% and 3.5%, pre-dark EV .59 and .51 (bias +.42, +.44), night .80 and .77. In the 240 s cycle with a 40 s night (n56, 0037), a 180 s game has no night and no dawn at all: dusk falls at 190 s.

**What it rules out.** A noise-only reading: with no sampling noise, and after 20 s of being held in the nest, the nim still walks out within about a second, so the policy at home is "leave", not a rare slip. A night-value reading: the night's value tracks its return as well as the day's, with no bias. That blending hides the reward for going home: with the colony blend at 0 the own return for going home is still not higher (-0.03 to -0.05, within about one SE), only about 0.03 less negative than blended. And that going home is a free gain the reward fails to see: it gives up apples. Steered home at 56 s the nim stores 0.15 (s1) and 0.41 (s2) fewer apples by dawn, 2 and 5 standard errors, and the food standing when night falls is gone until dawn, so what's lost is the last apple before nightfall. By Codex's reading of the tree code a stored apple pays 1 to each living nim and the blend doesn't touch that, so the loss is as big as or bigger than the 0.03 to 0.08 the return falls by, the shelter pay making up the rest. That reads as most of the cost of going home; the return isn't split apple by apple, so it's not measured.

**Limits.** Two brains of one recipe, one dusk time (56 s) and one 20 s steer. `confirmed` because all three seed blocks are fresh and the dusk numbers repeat 0035's probe on the parents (cost 0.04 and 0.06, dawn survival up 17 to 19 points); the firm parts are the dawn gain (3.5 standard errors on each seed) and the leave-in-a-second, while the return gap is small (inside one to two standard errors on any one brain). The stored-apple count runs to dawn, not only the 20 s after dusk, and counts apples stored, not apples eaten. The held nims are not a clean paired sample at 20 s: the mate pushes many out of the nest during the hold (61 to 21, 50 to 8 still home at release), so the survival gain at 20 s (+0.164 on s1) is among those and a hint. The explained variance is a single sampled return per state. The value's pre-dark gap is one phase of one world, a hint. The n49 dusk probe of 0035 found the same trade (return -0.04 and -0.06, dawn survival +17 to +19) on the parents; this repeats it on the n52 controls.

**Replays and clips.** None.

**Links.** 0017 (the pass-through nest); 0018, 0019 (pays for warmth, and for dawn); 0022 (charging for the cold); 0035 (the parents' dusk probe, this on the controls); 0037 (why the night worlds never made staying out cost). Codex's report: `2026-11-10-codex-night2/report.md`.
