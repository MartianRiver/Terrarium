# 0041 Sight does the work: the 12 m night brains live as long as they can see, and training at 8, 6 or 4 m doesn't teach them to make up for it

date: 2026-11-11 · status: confirmed · seeds: 9,940,000 × 256 (first use: the 12 m result, four seeds, and three nights); 9,980,000 × 256 (the block that chose the night rungs: the work-back and the skip-ahead) · brains: n70b-vision12-s1 and -s2 and n70d-vision12-s3 and -s4 (8M from n52-ctl at 12 m, seeds 661 to 664); n71-vision8 and n71-vision6 s1 and s2, n71b-v12to4 s1 and s2 (8M more from the 12 m brains at 8, 6 and 4 m); against n58-ctl s1 and s2

**Question.** 0040 found that trained with 12 m sight the night brains live the night. Does that hold on fresh seeds and more of them, and is the 12 m world a step to work back from: do brains taken from it to 8, 6 and 4 m keep living?

**World and brains.** The night world of 0040 (one colony of two, the tree up to 12 m from the nest, 60 s nights), at vision 12, 8, 6 and 4 m, nothing else changed. Seeds 3 and 4 at 12 m share their parents and seeds with the twin controls of 0039 (n64-ctl-t3 and -t4). The work-back trains the 12 m brains 8M more at 8 m and at 6 m; the skip-ahead, 8M more at 4 m, the target world.

**Method.** `mates.py`, 256 games × 300 s (360 s for three nights), alive at the end. Each brain in its own sight; the 12 m brains frozen beside the brains trained at 8 and 6 m, in those worlds; n58-ctl beside them. The scripted nim of 0015 on the same games as the ceiling.

**Result.**

| sight | trained there | the 12 m brains, frozen | n58-ctl | seeds |
|---|---|---|---|---|
| 12 m, two nights | 90%, 89%, 83%, 78% | | 35%, 46% | 9,940,000 |
| 12 m, three nights (360 s) | | 88%, 86% | 30%, 41% | 9,940,000 |
| 8 m | 65%, 71% | 71%, 80% | 39%, 60% | 9,980,000 |
| 6 m | 52%, 66% | 53%, 66% | 41%, 58% | 9,980,000 |
| 4 m (the target) | 46%, 41% | 32%, 45% | about 45% (0039) | 9,980,000 |

On a fresh block, all four seeds trained at 12 m live the night (78 to 90%) where the control lives 35 to 46%, and the first two carry through a third night they never trained for (86 to 88%). Below 12 m, survival falls with sight, and 8M of training at the shorter sight lifts nothing over the 12 m brains played frozen there: at 8 m it is a few points below them, at 6 m level, and at 4 m the brains are back where the control is. With the 12 m sight they find the tree; without it they don't learn another way to.

**What it rules out.** That the 12 m world, worked back from as tested here (8M a step), is a curriculum step toward 4 m: what the brains learned there doesn't survive taking the sight away, one step at a time or all at once. That the tested 8M work-back recipes teach a stand-in (remembering where the tree is, walking straight to it): nothing beat the frozen 12 m brains.

**Limits.** The work-back and skip-ahead are two seeds each, on the block that chose the night rungs, once; the 12 m result and three nights are on a fresh block. 8M is one length of training; a longer run, or memory built for it, could still teach a stand-in. Seeds 3 and 4 sit a few points under 1 and 2 at 12 m. The scripted nim lives 100% at 12 m, so there is headroom. Sight range also sets the scale of the brain's home-distance input and its ray distances (both are divided by it in `forage.py`), so a brain moved to a shorter sight reads home and everything it sees on a different scale: part of the fall below 12 m may come from that, not from the sight alone. These brains saw blocks through the middle of each ray only: a trunk 10 m off showed at about a quarter of headings, where berries and nims showed anywhere in a ray's slice (fixed in #171, so brains trained since see trunks far more often).

**Replays and clips.** None yet.

**Links.** 0040 (the night block is the far tree); 0001, 0004, 0013 (the notes and the tree's place); 0015 (the scripted nim).
