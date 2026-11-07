# 0011 Ask what a frozen brain can show before training a twin

date: 2026-11-06 · status: confirmed · seeds: 8,102,000, 8,103,000 · brains: mid2-s1, s2, s3 (one family)

**Question.** Do blank notes cost a trained brain only the information in them, or also the shock of a strange state? The proposed control was twin training, with and without unload wipes.

**World and brains.** The proposed control: three seed pairs of 8M, six chunks of 23–31 minutes, 48M samples. What was done instead: the frozen `mid2`-s1, s2 and s3 of 0004, no training.

**Method.** Matched note swaps (512 recipients each, seed 8,102,000) and a decode of the tree's place from the notes (3,000 games each, seed 8,103,000), both in 0004.

**Result.** Notes from another game at the same place did as well as the brain's own (within 0.1–0.8 s of a 17–22 s trip). Wrong-place notes did worse than none. So blank costs the information, not a shock. The run took about ten minutes of Mac CPU and no PPO samples.

**What it rules out.** That the 48M twin-training control was needed to answer this question: it would have cost six chunks of 23–31 minutes each, and the frozen swap and decode answered it first. The same run named what couldn't be said (see Limits in 0004).

**Limits.** This settles the shock question for the first deposit in one world and three brains of one family. It doesn't say that a frozen test replaces training for every question; it cost nothing here because the frozen brains had something to read. The wall time is the notes' own figure ("about ten minutes"), not a measured log.

**Replays and clips.** None kept.

**Links.** `../notes/efficiency.md`, "Not measured yet" (the frozen causal test); `../notes/0.4.md`, "A tree they go back to: what the notes hold"; 0004.
