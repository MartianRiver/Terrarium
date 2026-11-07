# 0009 The frozen colony exam fails on staying alive before memory can show

date: 2026-11-06 · status: hint · seeds: seed 1, eight arenas each · brains: grown-s2 (and the meals-free brains), against the 0.3 brain

**Question.** Before any training in the colony world, do the tree brains' memory skills carry over to `configs/colony.toml` as it is?

**World and brains.** Three colonies of six, 360 s, nights, food in patches, move costs. The weights frozen; notes kept or wiped as each one unloads. grown-s2 is the one tabled; the meals-free brains were also run. The 0.3 brain, which has no memory, is the reference. Do they go back to patches they've found, do they live, do the stores grow.

**Method.** Eight arenas each from seed 1: a first look only. Four versions of the colony world: as it is, no nights, no move costs with full energy at the start, and neither.

**Result.** Alive at the end:

| colony world | grown-s2 (kept / wiped) | 0.3 brain |
|---|---|---|
| as it is | 0% / 0% | 65% |
| no nights | 22% / 22% | 53% |
| no move costs, full energy at the start | 0% / 1% | 99% |
| neither | 62% / 66% | 97% |

The meals-free brains do no better: 0–1% as it is, 49–61% with both off. Going back to a known patch: 90 against 92% for notes kept against wiped, and the 0.3 brain goes back as often.

**What it rules out.** That this exam measures memory: it fails on staying alive first. Nights and the cost of moving each kill them on their own; with both gone a third still die by day with jelly in the store. Also that `colony.toml` asks for memory at all: patches often lie in sight of home and the rays see 8 m, so a brain with no memory does as well. An exam that reads memory needs food out of sight from home.

**Limits.** Seed 1, eight arenas, so a hint. Everything in the colony world is new to these brains: smell, the light, other colonies, sprint, a crop of two, sight to 8 m, games four times as long. So this is how far the memory carries, not how they'd do trained there. The planned fresh exam (256 colony arenas, zero training, returns, survival and the store separately) has not been run.

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "A tree they go back to: what the notes hold" ("The frozen colony exam", "Still to try"); 0007 and 0010.
