# 0043 The main world can be lived in, and water is what the colony brain lacks

date: 2026-11-11 · status: hint · seeds: 8,122,000 × 64 (the frozen start, 360 s), 8,124,000 × 64 (the scripted night check, three nights), 8,126,000 × 16 (the water drain check, 360 s), 8,127,000 × 32 (the 2M pilots); every block first use · brains: c2x9-more-s1 and -s2 (the colony brains, trained with no water), n70b-vision12-s1 (the 12 m night brain of 0041, the "v12 night brain"), four 2M pilots (m1-n64 from n70b, m1-c128 from c2x9-more-s1, m1-c256 the same widened, m1-f128 fresh); two scripted policies (`nester`, `ranger`) and five scripted night policies

**Question.** The main world puts every skill that works alone into one two-colony world. Can it be lived in at all, and what stops the brains we have from living there?

**World and brains.** `main-world.toml`: two colonies of nine, a 26 m world, four meadows (two near each nest, standing grazing only), one pond placed so neither nest is more than 1 m nearer, one apple tree (8 of the 30 foods), 60 s nights in a 120 s cycle with rest and sleep, fat, 12 m sight, hatching on. A full water bar lasts 83 s (drain .012 a second), and a night uses .72 of it, so a nim needs about .77 at dusk, .82 with margin; the pond is about 4 s from a nest. Frozen brains: the two c2x9-more colony brains (trained in a world with no water, so they never learned to drink) and n70b-vision12-s1 (night brain from 0041, trained with water off). Scripts: `nester` (stays home, never goes to the tree), `ranger` (a nester that also drinks and jumps for apples; a test instrument, nothing carried from it) and five scripted night policies, none of which drink.

**Method.** Frozen play, sampled actions. The start: 64 games × 360 s, 128 colonies a policy, seed 8,122,000. The night check: five scripted night policies (home-rest, out-still, out-wander, huddle-out, late-home), 64 arenas, three nights, seed 8,124,000. The water check: the c2x9-more-s1 and n70b-vision12-s1 brains at the real drain (.012), half of it (.006) and none, 16 games × 360 s (32 colonies a cell), seed 8,126,000. The pilots: four brains trained 2M samples each (40 updates) in the main world with every food paid alike (apples as any food), then 32 games (64 colonies), seed 8,127,000, the same probe. "Colony size" is the mean number alive in a colony at 360 s and counts hatchlings.

**Result.**

| frozen, 128 colonies, 360 s | colony size at end (of 9 at the start) | colonies alive | deaths: thirst / chilled / starved | mean life | drank / grazed |
|---|---|---|---|---|---|
| `nester` | 0.0 | 0 | 1010 / 26 / 125 | 81 s | 20% / 75% |
| `ranger` | 7.88 | 128 | 27 / 22 / 455 | 294 s | 98% / 95% |
| c2x9-more-s1 | 0.0 | 0 | 1309 / 22 / 74 | about 91 s | 35% / 74% |
| c2x9-more-s2 | 0.0 | 0 | 1363 / 26 / 40 | about 91 s | 36% / 72% |
| n70b-vision12-s1 | 0.0 | 0 | 634 / 238 / 377 | 78 s | 47% / 76% |

The world can be lived in: the `ranger` keeps both colonies in all 128 colony games. It isn't a clean pass: it records 504 deaths (mostly starvation, in the day, away from home) and 2.8 hatchings a colony, so the 7.88 is a colony kept up by replacement, not nearly all of its nine. Every brain ends with no colony. The colony brains die of thirst, 969 of their 1309 deaths (s1) at home in the dark, still for 88% of its time at home in the dark; only 35% of them ever drank. The night brain dies of thirst, cold and hunger in about equal parts, 238 of them chilled out in the dark, and is still for only 16% of its time at home in the dark. The scripted night policies, which never drink, are all dead by the first dawn: in three nights, none of the five has anyone alive at the first dawn, and 43 to 89% of each policy's nims die of thirst (the home-and-rest one 89%), the rest of cold or hunger.

Water is the wall for the colony brain:

| 16 games, 32 colonies, 360 s | water drain | colony size at end | colonies alive | deaths: thirst / chilled / starved | drank |
|---|---|---|---|---|---|
| c2x9-more-s1 | .012 (real) | 0.0 | 0 of 32 | 322 / 8 / 26 | 45% |
| c2x9-more-s1 | .006 (half) | 1.12 | 12 of 32 | 277 / 8 / 94 | 58% |
| c2x9-more-s1 | 0 | 9.62 | 32 of 32 | 0 / 15 / 149 | none |
| n70b-vision12-s1 | .012 | 0.0 | 0 of 32 | 137 / 86 / 83 | 54% |
| n70b-vision12-s1 | .006 | 0.0 | 0 of 32 | 2 / 108 / 197 | 55% |
| n70b-vision12-s1 | 0 | 0.0 | 0 of 32 | 0 / 128 / 179 | none |

With the water off the colony brain keeps every colony (9.62 a colony, hatchlings counted), at half the drain it keeps 12 of 32, at the real drain none. It loses 149 to hunger with the water off and still ends at 9.62 a colony, since hatchlings fill in. The night brain doesn't live at any drain: take the water away and it dies of cold and hunger instead (thirst 137, then 2, then 0), so it's a poor donor for this world: it has the tree and the 12 m sight but not the colony habits.

The four 2M pilots (40 updates each) move nothing on survival:

| pilot | start | colony size at end | colonies alive (of 64) | deaths: thirst / chilled / starved | mean life |
|---|---|---|---|---|---|
| m1-n64 | n70b | 0.0 | 0 | 312 / 116 / 189 | 77.9 s |
| m1-c128 | c2x9-more-s1 | 0.0 | 0 | 555 / 16 / 24 | 86.9 s |
| m1-c256 | c2x9-more-s1, widened to 256 | 0.0 | 0 | 556 / 5 / 23 | 88.0 s |
| m1-f128 | fresh | 0.02 | 1 | 513 / 50 / 12 | 98.5 s |

Their mean lives sit with their parents' (c2x9 about 91 s, the night brain 78 s, from a different seed block and the reward changed, so close in kind, not a paired comparison), the mix of deaths too, and the fresh brain is the same: thirst is 513 of its 575 deaths.

**What it rules out.** That the main world is out of reach: a script lives in it with both colonies in every game. That the colony brain is held back by the grass, the tree or its food: with the water off it lives in every colony. That 40 updates of the main world's training, from any of the four starts, is enough to move survival from a dead start (it moved nothing here; it isn't a statement about longer runs). That the night brain is the better donor: it dies at every drain.

**Limits.** `hint`: frozen brains only, 16 to 64 games a cell, one block each; the pilots are one seed a start, 2M samples, scored once on the one block. The water check is two brains at three drains; the half-drain row (12 of 32) rests on 32 colonies. The scripted night policies never drink, so what they show is that a nim can't get through a night without a drink, not that a night can't be lived in; the `ranger` is the only script that drinks, and I haven't checked that it uses only what a brain senses, so it shows the world allows survival, not that a brain can find the way to it. Survival counts at 360 s include hatchlings, as the `ranger`'s 7.88 and the colony brain's 9.62 do. The build's payoff ledger flagged an apple paid twice, and the pilots pay every food alike, so they aren't the recipe the frozen starts were trained in. Why 2M didn't move survival isn't split into too few updates, the wrong reward, or the brain. The 8,122,000 block was picked by hand, not taken from the ledger (now registered); 8,126,000 and 8,127,000 are registered on the battery-fixes branch, not here.

**Replays and clips.** None yet.

**Links.** 0030 (the pond nims stop to drink once the reward stops paying turnover: the colony brain never had that, trained with no water); 0031 (the grass nims stand to graze: the colony brains graze, 74% in the start); 0040, 0041 and 0042 (the 12 m night brains; n70b is one of them, and 0042's death split is the night brain's own); 0015 (a scripted nim lives through both nights); 0023 (180 s games teach drinking, half still die of thirst).
