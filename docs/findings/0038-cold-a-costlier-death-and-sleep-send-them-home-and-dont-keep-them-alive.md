# 0038 A harsher cold, a costlier death and sleep send the night brains home and don't keep them alive: no rung lifts survival past what the training seed alone moves it

date: 2026-11-11 · status: confirmed · seeds: 9,980,000 × 256 (choosing: every rung's first read); 9,990,000 × 256 (fresh, never used for choosing, scored once: the confirm table); home at dawn on 5 × 64 training-length games of sampled play; training seeds 661, 662 (s1, s2), 671, 672 (n60), 663 to 666 (twins t3 to t6) · brains: from n52-ctl-s1 and -s2 (0035), 8M each rung: n58-ctl, n58-cold03, n58-cold06, n58-dark, n59-r10, n60-ctl and n60-cold06 (+8M), n61-death5, n62-cold06 (+8M more), n62-cold02, n63-sleep, n64-sleep and n64-ctl twins t3 to t6, n64-sleepmore, n65-sleep10

**Question.** 0037 left the night brains walking out into the dark and dying 10 to 50 s into it, inside their reach. Each rung here changes one thing against a matched control: a harsher cold in training, a costlier death, a decision every 0.5 s (a longer reach), games that start at nightfall, and sleep (a still nim at home in the dark loses less). Does any teach them to come home, and do they live longer for it?

**World and brains.** The night world of 0037 (one colony of two, apple tree with burrow, 120 s cycle, 60 s night, dusk 10 s, cold .005, drain .0125, jelly .4 eaten from the store below .6, `needs` 1.0, gamma .99 at repeat 4, training games 180 s), one change each, every brain scored in that world:
- cold: .03 or .06 in training instead of .005 (n58); 8M more at .06 (n60, with n60-ctl, 8M more of the control); 8M more again (n62-cold06); n60-cold06-s1 eased to .02 (n62-cold02).
- a costlier death: −5 instead of −1 (n61).
- games start at nightfall (n58-dark), as 0019.
- a decision every 0.5 s (n59, repeat 10, the same 8M samples as 3.2M decisions): about 50 s of reach at gamma .99 instead of 20.
- sleep (n63, n64, n65; the merged body at next 5182323, v22 brains grown to v23): `[energy] sleep` .33, `still` .3, so a nim still in the dark and warm (in its own nest or huddled) loses a third of the drain (n65 a tenth). Six twin pairs, sleep and control from the same parent and the same training seed: n63-sleep against n58-ctl, and n64 t3 to t6. n64-sleepmore is n63-sleep + 8M more.

**Method.** Scores with `mates.py` (as 0035 and 0037), 256 games × 300 s (two nights), the same games for every brain in a block. Alive at the end, kept / self / both as in 0035. Every rung was read first on 9,980,000; the brains of the cold, death and sleep rungs and their controls were then scored once on 9,990,000. Home at dawn: the share of the living nims inside their own nest at each dawn, Codex's test 3 from 0036 (`home_at_dawn.py`, in the brain's training world).

**Result.** On the fresh block, 9,990,000, alive at the end, kept / self / both, s1 then s2:

| brain | s1 | s2 | rung minus control, s1 | rung minus control, s2 |
|---|---|---|---|---|
| n58-ctl | 45 / 42 / 35 | 49 / 37 / 36 | | |
| n58-cold03 | 42 / 37 / 33 | 54 / 46 / 47 | −3 / −5 / −2 | +5 / +9 / +11 |
| n58-cold06 | 39 / 34 / 32 | 54 / 51 / 47 | −6 / −8 / −3 | +5 / +14 / +11 |
| n61-death5 | 43 / 40 / 37 | 45 / 43 / 37 | −2 / −2 / +2 | −4 / +6 / +1 |
| n60-ctl | 46 / 37 / 38 | 53 / 45 / 44 | | |
| n60-cold06 | 42 / 40 / 34 | 50 / 52 / 47 | −4 / +3 / −4 | −3 / +7 / +3 |
| n62-cold06 | 31 / 31 / 32 | 49 / 50 / 45 | −15 / −6 / −6 | −4 / +5 / +1 |
| n62-cold02 | 41 / 40 / 32 | | −5 / +3 / −6 | |

n58 and n61 are read against n58-ctl, n60 and n62 against n60-ctl. n58-ctl-s2 reads low on both blocks: n60-ctl-s2, the same parent with 8M more, is 53 / 45 / 44, and against it the cold arms of s2 are +1 / +1 / +3 (cold03) and +1 / +6 / +3 (cold06).

The six sleep twin pairs, sleep minus control, kept / self / both:

| pair | 9,980,000 | 9,990,000 |
|---|---|---|
| n63 s1 / n58-ctl-s1 | +5 / +4 / +4 | +4 / +3 / +3 |
| n63 s2 / n58-ctl-s2 | −1 / +15 / +15 | +3 / +13 / +13 |
| t3 | +1 / +8 / +3 | +1 / +5 / +3 |
| t4 | −8 / 0 / −5 | −11 / −7 / −5 |
| t5 | +1 / +6 / +2 | +3 / +3 / +1 |
| t6 | −7 / −1 / +2 | −15 / −4 / +1 |
| mean | −1.5 / +5.3 / +3.5 | −2.5 / +2.2 / +2.7 |

The two controls t3 and t4 and n58-ctl-s1 and -s2 share parents and recipe and differ only in training seed, and differ by 3 to 12 points (n58-ctl-s1 45 / 44 / 39, ctl-t3 42 / 32 / 33 on 9,980,000). The sleep pairs spread that wide (sd about 6.5 on the both row on 9,980,000, about 6 on 9,990,000), and their mean on the fresh block is +2 to +3 on self and both and −2.5 on kept. Sleep at a tenth of the drain (n65: 44 / 45 / 42, 51 / 32 / 35) lifts no more than at a third (n63: 50 / 48 / 43, 52 / 51 / 48), and n63 + 8M more (n64-sleepmore: 44 / 43 / 38, 47 / 41 / 39) falls back to n60-ctl's level (47 / 39 / 41, 50 / 45 / 42), all on 9,980,000.

Read on 9,980,000 only: n58-dark 47 / 42 / 43 and 31 / 20 / 19 against n58-ctl 45 / 44 / 39 and 53 / 36 / 33 (no lift, s2 much worse, as 0019); n59 (a decision every 0.5 s) 27 / 24 / 29 and 27 / 22 / 23, about half the control at the same game time.

Home at dawn, share of the living nims in their own nest, s1 / s2:

| brain | home at dawn | control |
|---|---|---|
| n58-cold03 | 9.9 / 8.2% | n58-ctl 6.9 / 3.9% |
| n58-cold06 | 17.1 / 6.8% | n58-ctl 6.9 / 3.9% |
| n60-cold06 (16M at .06) | 49.2 / 5.9% | n60-ctl 9.2 / 3.9% |
| n62-cold06 (24M at .06) | 57.7 / 6.5% | n60-ctl 9.2 / 3.9% |
| n62-cold02 (eased) | 16.4% | n60-ctl 9.2% |
| n61-death5 | 29.0 / 4.0% | n58-ctl 6.9 / 3.9% |
| sleep twins, six pairs | 18.9 vs 8.1, 5.3 vs 2.9, 15.0 vs 8.8, 6.3 vs 3.7 (t3 to t6), 11.7 vs 6.9, 7.5 vs 3.9 (n63) | |

The cold sends s1 home, more the longer and harder (17 to 49 to 58%), and loses it when eased (16%); a death at −5 sends s1 home (29%); neither sends s2. Sleep doubles home at dawn on all six pairs. None of these brains lives longer for being home: n60-cold06-s1, home at 49%, is 42 / 40 / 34 against its control's 46 / 37 / 38 on the fresh block, and n62-cold06-s1, home at 58%, is the worst brain here.

**What it rules out.** That a harsher cold, a costlier death, sleep, games that start at nightfall or a decision every 0.5 s lift the night brains' survival in 8M to 24M: on the fresh block every rung is within the 3 to 12 points the training seed alone moves a brain, the one rung with a lift on both seeds on the choosing block (sleep) shrinks to +2 to +3 on self and both and −2.5 on kept, and s2's cold lift shrinks to +1 to +6 against the s2 control that doesn't read low. That being home at dawn is what they're missing: the cold, a costlier death and sleep all raise it, up to eight times, and survival doesn't follow. Where the deaths do come from is 0039.

**Limits.** Each rung is 8M (16M and 24M for the cold) on two parents; a single pair at 8M can't see a ±5 effect, so a small real lift from sleep (+2 to +3) isn't ruled out, only one big enough to matter for the 85% gate. n58-dark and n59 were read on the choosing block only. Home at dawn is sampled play on training-length games, five batches of 64; the alive rows are 300 s. n58, n60, n61 and n62 trained on the body before the merge (v22) and the sleep brains on the merged body (v23); the twin controls t3 to t6 are v23, so the twin pairs are matched, and n63 s1 and s2 against n58-ctl are not.

**Replays and clips.** night-home-and-stays (n60-cold06-s1 in the plain night world, seed 51, 54 to 72 s, nim 2: home at lights-out and in until about 114 s), flagged in backups `lab/channel/highlights.toml`; not cut.

**Links.** 0015 (a scripted nim lives through both nights); 0017 (the pass-through nest); 0019 (starting at nightfall); 0022 (charging for the cold); 0035 (the spread reset; a longer horizon); 0036 (the dusk trade); 0037 (deaths 10 to 50 s into the dark); 0039 (the deaths come down to food).
