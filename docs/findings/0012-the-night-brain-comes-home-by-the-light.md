# 0012 The night-trained brain comes home by the light; the day-trained ones die whatever their start

date: 2026-11-07 · status: hint · seeds: 8,108,000 · brains: j180-s1, j180-s3, nightq2-s2 (last checkpoints, 8.0M samples)

**Question.** In the colony nights world (`nightq/world.toml`), with no more training, which link fails at night: eating the store when hungry at home, getting home from outside or from far, having something in the crop at dusk, or reading the light?

**World and brains.** The 7 Nov night world: one colony of two, 180 s games, a 60 s night in a 120 s cycle (dusk 10 s), cold 0.005, the apple tree with burrow, jelly 0.4, drain 0.0125 a second. j180-s1 and s3 were trained without nights; nightq2-s2 was trained in it. Weights frozen, notes kept, 128 note slots each, yes/no actions drawn as a coin as in the evals.

**Method.** 256 games a cell, the same games for every brain and condition (world and action noise per game from the seed), every condition paired to the control by game with a 95% bootstrap over games. Starts set through World arrays and `physics.revive`. Control: the world as is. A: energy 0.5 and 6 jelly in the store at tick 0, in the nest, by day. B: A, 1.5 m outside the nest's rim, facing away. C: energy 0.5, 6 jelly, 7 m from the nest's middle, every apple removed and regrowth held 40 s. D: an apple in every living crop at 50 s, where the light starts to fall. E: the light entry of the observation held at 1.0 all game; the world's light, the cold and the food untouched. The script and per-game arrays are kept in the lab folder, outside the repo.

**Result.** Alive at the end (share of nims), and the change against control with its 95% interval:

| | control | A hungry in nest | B 1.5 m out | C 7 m out, no apples | D apple at dusk | E light held at 1 |
|---|---|---|---|---|---|---|
| j180-s1 | 6% | +9 [+6, +12] | +7 [+4, +10] | -3 [-5, 0] | +3 [+1, +6] | -2 [-4, +1] |
| j180-s3 | 2% | +1 [0, +3] | 0 [-2, +2] | -2 [-3, -1] | +1 [-1, +3] | +5 [+3, +7] |
| nightq2-s2 | 60% | +14 [+9, +18] | +12 [+7, +16] | **-46 [-52, -41]** | +4 [0, +7] | **-60 [-64, -55]** |

Where they die (control): 92–100% in the dark, a median 6.4–8.5 m from the nest's middle (73–85% past 4 m, under 5% inside the rim), with jelly in the store in 79% (j180-s1), 96% (s3) and 70% (nightq2-s2) of the deaths and almost never anything in the crop. Hungry at home with an empty crop and jelly in the store, the eat yes-rate is 3–7% of ticks in every condition of every brain (a rate until the first jelly, not a chance of ever eating); the jelly eaten from the store goes up with a full store (+0.46 to +0.62 energy a nim in A for all three, +0.29 to +0.48 in B) and falls by 0.54–0.82 in C, where few reach it. Getting into the nest: from 1.5 m out (B) the first entry takes 24–34 s on average, though 89–94% get there; from 7 m (C) 15%, 0% and 33% got there before they died, at 38 s (energy 0.5 less drain and jumps), with 6 jelly at home 6 m off.

**What it rules out.** Only for nightq2-s2, the one brain with something to lose: that it dies for want of an apple in the crop at dusk (D, +4, the interval touches 0; 31% already carried one at 50 s), or of knowing how to eat the store (eating isn't the move, A and B are better than control). Its night depends on the light reading: with it held at 1.0 the share alive goes 60% to 0%, all dying in the dark far out, so the link is the light telling it to come home and stay. Hungry and far away by day it doesn't come home to the jelly either (C, -46). For j180-s1 and s3 it rules out that any one of these patched starts is what keeps them from living: none moves them by 20 points, and nothing moves them far (control 6% and 2%).

**Limits.** One seed, 256 games, three brains from two training families and no twin of nightq2-s2 (s1 and s3 weren't run), so a hint about that family, not a result about the night. j180 brains sit at the floor: a condition that would hurt has nothing to hurt, and the 20-point rule can only see rescues for them. C is lethal by arithmetic: 0.5 energy at 0.0125 a second is 40 s, the length of the hold, so a nim that doesn't head for the jelly dies at 38 s whatever the hold; C was given the 6 jelly of A and B so the store is there to reach. C and E also differ from control in more than one thing (C: hunger, distance and no apples; A is its nearer comparison). B and C use a direction drawn for each game and put the two nims side by side a body's width apart (the nest spawn puts both on one point); C keeps the game's random heading, B faces away. D's 50 s is where the light starts to fall, taken as the first dusk. Energy from the store is jelly eaten times 0.4 before the clip at full. E hides the light only from the brain: the cold, the food vanishing at nightfall and the nest warmth all still happen.

**Replays and clips.** None kept.

**Links.** `../notes/0.4.md`, "Longer games, then nights"; 0009 and 0010 (the frozen colony exam, nothing paid for a meal in the night forks); 0011 (why a frozen brain was asked first).
