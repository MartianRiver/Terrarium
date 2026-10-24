# Evals

How a brain is scored. A policy plays 64 episodes, one per arena, all from seed 1,000,000, which no training run uses. Each episode runs until everyone in it is dead or `[episode] seconds` is up. Every creature gets two numbers:

- **food per minute** of its own life
- **seconds alive**, which tops out at the episode length

Each is reported as a mean ± standard error over the creatures.

```
cd sim
uv run python -m terrarium.evals --policy random greedy --config configs/solo.toml [--out results.json]
```

`random` is the stand-in brain from 0.1, and the baseline every trained brain has to beat. `greedy` is scripted: it heads for the nearest food any ray sees, and otherwise goes straight and turns away from anything close ahead. It's not a brain and never trains anything. It shows what the senses make possible, so if a trained brain can't get near it, the brain is the problem, not the rays.

From 0.3 greedy also eats what it carries once it can without waste, and `carrier` is greedy that takes its crop home and unloads it once it's full, and goes home to eat when it's hungry and the store has jelly. Results also have **stored**, food unloaded into the creature's own store. Food per minute counts food picked up where it grew, eaten or carried. Since a full Terrikin with a full crop can't take any more, 0.3's numbers can't be compared with 0.2's: the 0.2 brain scores 5.23 solo in the 0.3 world against 18.40 in its own. The numbers and how they changed are in [notes/0.3.md](notes/0.3.md).

## v1, solo forager (0.2)

`configs/solo.toml`, 64 episodes of up to 180 s:

| policy | food per minute | seconds alive |
|---|---|---|
| random | 0.26 ± 0.07 | 49.6 ± 2.1 |
| greedy | 13.79 ± 0.16 | 180.0 ± 0.0 |
| 0.2 brain (`17cc35ad7932`) | 18.40 ± 0.14 | 180.0 ± 0.0 |

The promoted brain lives every episode out and eats a third more than greedy. Its worst episode (14.7 food per minute) beats greedy's mean.

The food count was set from these, by running both policies at a few counts:

| food | random | greedy |
|---|---|---|
| 28 | 0.86 / 70 s | 37.2 / 180 s |
| 12 | 0.46 / 57 s | 19.6 / 180 s |
| 8 | 0.26 / 50 s | 13.8 / 180 s |
| 5 | 0.15 / 47 s | 9.0 / 174 s (some die) |

At 8, random actions starve within a minute and good foraging lives the whole episode, so time alive separates them as well as food does. If training struggles to get started because meals are too rare at first, this is the dial to turn up.

A brain clearly beats random when its food per minute is at least twice random's, and both its numbers are ahead by more than three standard errors of the difference. `promote` holds a brain to this. The scores of the promoted brain go in its lineage entry.
