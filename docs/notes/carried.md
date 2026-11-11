# What the main world carries

Every thing a side line learned that made nims better or training cheaper, and whether the main world has it. Read it before planning a rung on the main line; a rung's card names the "not yet" lines it takes on. A finding that shows something working adds a line the same day. Settled lines move to the bottom.

The main world was the 12 m night world (`world-vision12`, train `train-needs`) until 11 Nov; from 11 Nov it's the two-colony world with every nursery skill (branch main-world). Lines below were checked against the night world on 11 Nov.

`what | finding | status | keys or reason | last checked`

## Not yet

- thrust that can sample a stop: bound on the thrust mean | 0028, 0032 | not yet | `[ppo] bound 0.01`, `bound_for ["thrust"]`; night brains' thrust std .145, turn .028, mean past the clip; 0035 tried only 0.001; r2 (2M, s1): 92 vs 90% alive, night-1 deaths 0.2 vs 2.9%, home 26 vs 17% of the night, still only 6%: harmless, leans right; into the main world | 11 Nov, r2
- steering spread reset (turn-only, or 0.10–0.35) | 0032, 0034 | not yet | a checkpoint edit of `log_std`; 0.35 on both cost the 4 m night brains half their survivors (0035); 0.2 at 12 m cost them too at 2M (r2: 56 and 82% against 90/94): leave out of the main world for now | 11 Nov, r2
- stopping pays: rest and sleep | 0028 (colony c29 rests 16–21 s a minute) | not yet | `[energy] rest 0.5`, `sleep 0.2`, `still 0.1`; useless on a pinned thrust; with the bound, into the main world | 11 Nov, r2
- walking costs | 0026, colony 9 Nov | not yet | `[energy] move 0.01`; frozen on pinned night brains it took s1/s2 from 90/94 to 36/42% alive, so only after the unpin | 11 Nov
- training games hold the whole exam | 0023, ledger 11 Nov | not yet | `[episode] seconds` 180 in training, 300 in the exam: night 2 is never trained | 11 Nov
- hunger felt all the time | 0030, 0031 | not yet | `[reward] hunger 1`; scale `[tree] points` with any `needs` x3–6 or delivery shrinks | 11 Nov
- a fresh brain beside the fork | efficiency.md, 0.4 | not yet | the night line is all forks; one fresh run, 4 m, 0% | 11 Nov
- a wider brain beside the working one | standing rule, widen.py | not yet | night brains are width 64, colony 128; the main line trains 256 beside | 11 Nov
- state-dependent spread | (design) | not yet | branch in ../Terrarium-statespread, unreviewed | 11 Nov

## Carried

- grass that takes standing still | 0031, 0032 | carried | `[grass] still 4`, two meadows near each nest, none in the dark (`night 0`) | 11 Nov, main world
- drinking takes stillness | 0030 | carried | `[water] still 4`, one pond fair to both nests; the pond worlds' costs were babies' (1%), the main world keeps ab-2x9's | 11 Nov, main world
- sight long enough to find the tree | 0040, 0041 | carried | `[vision] range 12` | 11 Nov
- turnover-neutral reward | 0030 | carried | `needs_lost = needs` (1.0 / 1.0) | 8 Nov
- a decision every 0.2 s | efficiency.md | carried | `repeat 4` | 3 Nov
- lr 5e-5 for forks | 0003 | carried | `lr 5e-5` | 6 Nov
- 180 s games over 90 s | 0023 | carried | | 11 Nov
- frozen tests before training, seed blocks from the ledger | 0011, docs/seeds.toml | carried | `terrarium.seeds take` | 11 Nov

## Not needed

- tree scent at 4 m sight | n72 | not needed | 12 m sight does more; revisit for trails | 11 Nov
- world dials that rescue the untrained brain but teach nothing | 0026, 0039, 0040 | not needed | they change the exam | 11 Nov
- tried at night and flat: chill input / chill_time, dawn pay, pay for warmth, full cold in training, costlier death, shorter night, `work` 0.005, games from nightfall, 0.5 s decisions, gamma .995/.998 on pinned brains, more of the same 8M | 0018–0020, 0037, 0038, 0039 | not needed on a pinned brain | retest gamma only after the unpin | 11 Nov
