# 0016 Three colonies of six end bigger than one of eighteen on the same food, and don't cost each other

date: 2026-11-08 · status: confirmed · seeds: 2,000,000 × 256 (all), 8,113,000 × 256 (frozen, and the first 8M of 1×18 s1, fresh) · brains: the 0.3 brain c1c16fc46934; ab-3x6-s1..3, ab-1x18-s1..3 (8M each on it); ab2-3x6-s1/s2, ab2-1x18-s1/s2 (8M more each on its own ab brain)

**Question.** River's: with each nim carrying its own copy of the same brain, do three colonies in one world fight themselves, so that one colony of the same nims would do better on the same food?

**World and brains.** The colonies world (`colony.toml`, 0.3's main world: 22 food in patches, nights of 120 s cycles, hatching, nectar flowers, 360 s games). Two versions that differ in one thing: 3×6, three colonies of six (room 2 each, nest radius 1.6 m), and 1×18, one colony of eighteen on the same 22 food (room 6, nest radius 2.77 m, √3 as wide for three times the nims). The 0.3 brain was trained in 3×6. Each arm was then trained 8M samples on 0.3's recipe (`train-03.toml`) in its own world, three seeds, and two seeds a second 8M from those.

**Method.** `terrarium.evals --held-out --episodes 256`, every brain in both worlds, the same games for every brain. The number is a colony's size at 360 s over its size at the start (6 or 18), mean over colonies and games. The standard error of the 1×18 end is about 0.008 of its start, and of a 3×6 colony's about 0.005. The frozen brain and the first 8M of 1×18 s1 were played again on fresh block 8,113,000.

**Result.** End size over start (held-out 2,000,000; fresh 8,113,000 in brackets):

| brain | trained in | in 3×6 | in 1×18 |
|---|---|---|---|
| 0.3, frozen | 3×6 (0.3) | 1.047 (1.038) | 0.713 (0.707) |
| ab-3x6 s1 / s2 / s3, +8M | 3×6 | 1.057 / 1.047 / 1.049 | 0.710 / 0.722 / 0.711 |
| ab-1x18 s1 / s2 / s3, +8M | 1×18 | 1.054 (1.049) / 1.063 / 1.064 | 0.872 (0.866) / 0.849 / 0.853 |
| ab2-3x6 s1 / s2, +16M | 3×6 | 1.073 / 1.060 | 0.775 / 0.746 |
| ab2-1x18 s1 / s2, +16M | 1×18 | 1.060 / 1.060 | 0.949 / 0.898 |

Frozen, the three colonies of six grow (1.047, none of 768 colonies lost, 6.41 / 6.25 / 6.18 at the end, so even), and one colony of eighteen shrinks to 0.713, 12.8 nims of 18 where the three end with 18.8. Training in 1×18 lifts it to 0.85 to 0.87 in 8M and 0.90 to 0.95 in 16M, and the brain it makes is no worse in 3×6 (1.05 to 1.06). Three colonies still end higher than one after the same training: the gap goes from 0.33 frozen to 0.18 to 0.21 after 8M and 0.11 to 0.16 after 16M, every seed.

**What it rules out.** That same-brain colonies cost each other: three colonies of six grow evenly and end bigger than one colony of the same eighteen nims on the same food, frozen and after up to 16M in either world. That the 1×18 shortfall is only a brain trained elsewhere: training in 1×18 narrows it but hasn't closed it.

**Limits.** One food setting (22) and one split (3×6 against 1×18). The single nest is wider but still one place, so trips are longer for most foragers and one nest's crowding is in the 1×18 number along with whatever one colony does differently; this doesn't separate the two. The 16M row is held-out only and two seeds, and the 1×18 line was still climbing at 16M, so whether it would catch up with more training is open.

**Replays and clips.** The channel's Colonies nursery shows ab2-3x6 and ab2-1x18 (backups `lab/channel/live/`).

**Links.** 0009 (the frozen colony exam); `../notes/0.3.md`; `../../ROADMAP.md`, 0.4.
