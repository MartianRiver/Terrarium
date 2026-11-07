# 0003 In the burrow world they learn to use their notes

date: 2026-11-06 · status: held-out · seeds: held-out 64, fresh 9,000,000 × 128 · brains: tb, tbc, tbh seeds 1–3 from lam99-s2 (one family)

**Question.** In the burrow world, where the body no longer points back at the tree (0002), do trained brains learn to use their notes?

**World and brains.** `[tree] start` 1.5, `burrow`, ±12 m, 32 m arena, 90 s games. Training 8M samples a chunk from lam99-s2, three seeds; later chunks at learning rate 5e-5 (from 1e-4), named `tbh`, `tbhc`, `tbhd`.

**Method.** Apples home a minute, notes kept / wiped on unloading, 64 held-out games, then fresh games (seeds 9,000,000 × 128; picker 5.75, searcher 2.40). In brackets the paired gap (kept less wiped, bootstrapped over games). Held-out picker 5.97, searcher 3.35, `tree_seen` 4.16.

**Result.** Held-out, kept / wiped (gap):

| after | seed 1 | seed 2 |
|---|---|---|
| parent (lam99-s2) | 3.31 / 3.20 (+0.12 [−0.17, 0.42]) | |
| `tb`, 8M | 4.19 / 3.60 (+0.58 [0.23, 0.94]) | 4.68 / 4.12 (+0.56 [0.28, 0.81]) |
| `tbc`, 16M | 4.86 (+0.78 [0.41, 1.17]) | 5.12 (+1.17 [0.75, 1.61]) |
| `tbc2`, 24M | 4.84 / 3.79 (+1.05 [0.66, 1.47]) | 5.24 / 4.18 (+1.06 [0.85, 1.28]) |
| `tbh`, +8M at lr 5e-5 | 5.17 / 3.22 (+1.95 [1.39, 2.55]) | 5.23 / 4.34 (+0.89) |
| `tbhc`, +8M at 5e-5 | 5.50 / 4.02 (+1.48 [1.09, 1.90]) | 5.69 / 4.39 (+1.30 [0.95, 1.72]) |
| `tbhd`, +8M at 5e-5 | 5.42 / 4.11 | 5.68 / 4.26 |

Seed 3 (`tb`-s3) took 8M to 4.73 / 3.29 (+1.44 [0.91, 2.01]). On fresh games `tbhd`-s1 brings home 5.23 kept and 3.74 wiped (+1.49 [1.23, 1.76]), `tbhd`-s2 5.34 and 3.66 (+1.68 [1.35, 2.06]), and the third lineage (`tbc`-s3) 4.84 and 3.48 (+1.35 [1.04, 1.70]). Wiping on unloading costs 0.8–2.0 a minute from `tbc` on. With no help at all (`start` 0, which these brains never trained on) `tbc2`-s2 brings home 4.54 / 3.79 (searcher 2.95, 34 of 64 games never home).

**What it rules out.** That the notes gap is a quirk of the held-out seeds: it holds on fresh games. A side loss on the notes (0.01) gave nothing (one seed, gap +1.04 against +1.17 without). Sixteen million more samples of peekaboo at young speed 0.3 fell apart (3.81 → 2.00, wiped 1.12). 8M more with `start` 0 (`find`-s2) bought nothing: 4.34 / 3.36.

**Limits.** One family. The score flattened near 5.0–5.2 with the gap near 1.05; the lower learning rate lifted the plateau (`tbc2`-s2 5.24 → `tbhc`-s2 5.69, 0.95 of the picker held-out; on fresh games the best are 0.91 and 0.93 of the picker) and a third chunk was flat. The fresh block was later used for choosing and is retired. A wipe takes more than the place of the tree (trip phase, the clock), so this does not say what the notes hold; 0004 does. The tree always lay roughly south of the nest here. Scored before #115.

**Replays and clips.** `tbhd`-s2 with notes kept and wiped on unloading on ten fresh seeds were replayed, and three of the ten came out about even. Paths not recorded.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("Training in the burrow world"); #115; 0002 before, 0004 after.
