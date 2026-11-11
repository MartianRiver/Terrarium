# 0042 The 12 m night brains die two ways: out in the first night, and short of stock into the second dawn; two of six pass 85%

date: 2026-11-11 · status: confirmed · seeds: 8,119,000 × 256 (the exam, first use); 8,120,000 × 256 (the diagnosis, first use) · brains: n70b-vision12-s1 and -s2, n70d-vision12-s3 and -s4, n74-vision12-s5 and -s6 (8M from n52-ctl at 12 m); n58-ctl-s1 beside them; the scripted nim of 0015

**Question.** Do the 12 m night brains of 0041 pass 0.4.1 (85% alive after two full nights, three brains, fresh seeds)? Where they don't, when and why do the rest die?

**World and brains.** The 12 m night world of 0041 scored at 300 s (two nights, the third dawn). Six seeds of the same recipe, every one reported. The control and the scripted nim on the same games.

**Method.** The exam: `mates.py`, 256 games × 300 s, alive at the end, with notes kept, and with each nim's notes wiped whenever it unloads. The diagnosis, on a second fresh block: every death placed in a phase of the day (first night, dawn, second night, third dawn) and compared with the nims still alive at that moment, not over the game; the store at each dusk against who lived; games split by whether the tree can be seen from the nest; and forced counterfactuals, frozen, that each fix one thing at a set moment (the store topped up to 4 at dusk, energy raised to 0.6 at dawn, everyone put home at dusk, and pairs of these).

**Result.**

| | s1 | s2 | s3 | s4 | s5 | s6 | n58-ctl | script |
|---|---|---|---|---|---|---|---|---|
| exam, alive at 300 s (kept / wiped at unload) | 86.9 / 89.8 | 87.5 / 85.2 | 78.1 / 81.6 | 82.8 / 73.4 | 81.8 / 82.8 | 68.0 / 54.7 | | |
| diagnosis block, plain | 90.0 | 93.9 | 84.6 | 81.4 | 85.0 | 64.6 | 35.4 | 99.2 |
| store 4+ at dusk and dawn energy 0.6 | 95.1 | 97.3 | 97.9 | 93.4 | 92.6 | 69.5 | | |

Two of six pass 85% on the exam block (kept notes), and the mean is about 81%: 0.4.1 isn't met. On the second block, deaths come in two kinds. In the first night (6.3% of nims across the six; 20.7% for s6) they die chilled, away from home, with the nest still well stocked (8.7 against 9.1 for those who lived) and the same energy at dusk as the survivors. In the second night and third dawn (8.9%) they die because the store ran short: with 0, 1–2, 3–4 and 5 or more in the store at the second dusk, 6, 31, 80 and 96% live, and the dawn deaths come about 5 s after daybreak at an energy near 0. Topping the store up at dusk lifts the mean of six from 83.3 to 88.8%, energy at dawn to 89.1, both to 91.0 (92.6 to 97.9% for s1 to s5). Putting everyone home at dusk lowers it to 78.2. Games where the tree can't be seen from the nest are 12% of games and 45% of deaths. s6 differs from s1 mostly in the first night: at 120 s, 4% of s6's nims are home against 20% of s1's.

**What it rules out.** That the 12 m brains die for lack of food in the nest on the first night: the dying nests are as stocked as the living ones. That forcing them home fixes it: home at dusk made it worse (a guess as to why: the move leaves their notes out of date).

**Limits.** The counterfactuals are frozen and forced, not learned. No counterfactual was run for the first night (a warm nest, held at home). Why being put home hurt isn't traced. Stocking for the second night pays off 60 s or more after the choice, past the brains' ~20 s horizon at gamma 0.99 and 0.2 s decisions, and training games were 180 s long, so they never trained through a second dusk: both are readings of the code, not tests. These brains saw blocks through the middle of each ray only: a trunk 10 m off showed at about a quarter of headings, where berries and nims showed anywhere in a ray's slice (fixed in #171, so brains trained since see trunks far more often).

**Replays and clips.** None yet.

**Links.** 0041 (sight does the work); 0039 (the night deaths come down to food); 0015 (the scripted nim); 0014 and 0025 (a longer horizon cost before).
