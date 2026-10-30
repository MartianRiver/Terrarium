# Evals

How a brain is scored. A policy plays 64 episodes, one per arena, all from seed 1,000,000, which no training run uses. Each episode runs until everyone in it is dead or `[episode] seconds` is up. Every creature gets two numbers:

- **food per minute** of its own life
- **seconds alive**, which tops out at the episode length

Each is reported as a mean ± standard error. Since evals v2 (0.3) the error is over arenas, not creatures: creatures sharing an arena share its food and its luck, so 18 of them aren't 18 independent tries. Evals v1 counted every creature, which got colony errors wrong both ways: in the full world time alive's error is up to 60% bigger counted by arena, and food per minute's is half the size, since nestmates compete for the same food. Solo has one creature an arena, so its numbers didn't change. Each also gets a **p10**, the creature a tenth of the way up, because a good mean can hide a bad tail.

```
cd sim
uv run python -m terrarium.evals --policy random greedy --config configs/solo.toml [--brain X.pt] [--modes drawn mean sampled] [--held-out] [--device cuda] [--out results.json]
```

Each policy, and each brain in each mode, plays in its own process, side by side, sharing the CPU's threads. `--device` runs the brains on a GPU (training's own evals do on CUDA); the worlds stay on the CPU. On the CPU, a policy scored on its own or beside others gets exactly the same numbers as before. On a GPU the brain's arithmetic rounds a little differently, now and then an action comes out different, and the episodes drift apart from there: the same brain scored 265.0 ± 3.9 s alive on the CPU and 270.3 ± 3.7 on a GPU (night world, 64 episodes). That's within the noise, but not the same to the decimal, so brains being compared closely should be scored on the same device. All four sets took 11 minutes side by side on the CPU and 7 with the brains on the GPU (one after another, a vault run's took 30–40, in a slower world).

What else v2 counts, for colonies:

- **jelly** eaten from the store, per creature
- **deaths**: how many died, how many of them with jelly in their own store (**jelly home**, wherever they were), how many in their own nest, and whole **colonies lost** (left with nobody alive at some point). With hatching on a slot can die more than once, so these count deaths, not creatures
- with hatching on (`[hatch]`): **hatched**, Terrikins hatched per colony an episode, how many colonies hatched at least one (**hatching**), the colonies with someone alive when the episode ran its full length (**to the end**: in a three-day world, through all three nights), and **colony size**: Terrikins alive in each colony at the end, and the most it had at once
- with `[colonies] room` above 0, a colony starts with `size` and can hatch into the rest. Food per minute, seconds alive, food, stored and jelly are per *starting* place then (a place that starts empty would only pull the means down), so they stay comparable with worlds without room; what room adds shows in colony size
- with flowers on (`[flowers]`): **flowers** drunk per Terrikin, and how often a Terrikin that could sprint says yes with an open flower in its field of view (`sprint_flower`, beside `sprint_ready` for any time it could)
- with carry on (`[carry]`): berries **picked** up, **put home** (down inside its own nest), and **given** (a put-down berry later eaten by a nestmate, counted to whoever put it there) per Terrikin, with how many of those went to a hungry one; and how often it says yes to `carry` with a berry in reach (`carry_berry`) and while carrying (`carry_laden`). A carry yes only counts on the tick it changes from no, so these rates run higher than the toggles they make
- what the sprint and flowers get used for (`terrarium/tactics.py`), so we can see whether a brain spends its sprint where it pays or on getting about. Away from its own nest a Terrikin always has a best reason it could sprint, in this order: a **flower** in view, **food** in view, a run **home** it needs (hungry with jelly there, a full crop, or dusk falling, while facing home within 30°), or **about** (none of those). For each reason: how often it says yes when it's rested and could, what share of its sprints started there, and how many of those paid off (it ate, drank or got home within 3 s). Also sprints a minute away from home, flowers opened and the share drunk, how often a Terrikin with a flower in view heads straight at it (within 30°, over half thrust), and meals a minute away from home with the nectar boost on and off. The reasons are what it could see, not what it meant: food is in view most of the time, so `food` is the commonest reason even for a brain that sprints at random. Compare the yes rates between reasons, not the shares alone.

**Head to head** (`terrarium.versus`): one policy or brain per colony in the same arenas, racing for the same food. Nests aren't equally placed, so each takes every seat in turn over the same episodes, and its numbers are added up over its seats: colonies to the end and lost, and size at the end, hatched and seconds alive averaged.

```
uv run python -m terrarium.versus nester A.pt B.pt --config configs/colony.toml --held-out [--out results.json]
```
- how often each yes/no action says yes where it matters: `unload` at home with something in the crop, `unload` away from any nest with something in it (dumping), `eat` when hungry with something in the crop, and `eat` when hungry at home with jelly in the store (crop or not: a carrier unloads and eats on the same tick), `sprint` whenever it's rested and could, and `grab` whenever a block is within reach
- **turning**: the mean of turn squared (what turning costs by) out by day and in its own nest at night, to see spinning go
- **away by day**: deaths away from its own nest in full daylight, when food is out and there's no cold: a forager that couldn't keep itself fed
- **contested**: the share of meals eaten with a creature of another colony within 1.5 m of the food as it went
- **from the middle**: food eaten from the patches in the middle of the arena, per arena (in the vault, food only a door opened gets to), and **blocks moved**: how many blocks ended an episode more than half a metre from where they started

A brain steers by its mean action, so the evals score what it's learned rather than its exploration. Its yes/no actions (`unload`, `eat`, `sprint`, `grab`) are drawn instead, at the odds the brain gives them, with seeded noise so the numbers repeat: a yes/no action taken by its mean is never yes until the brain is sure, and in 0.3 that hid a brain that couldn't eat on purpose ([notes/0.3.md](notes/0.3.md), "Evals v2"). Replays use the same. `--modes mean` scores it all by the mean, the way evals v1 did, and `--modes sampled` with everything drawn, as in training. Training ends by scoring the last checkpoint all three ways.

`--wiped` also scores each brain with its memory wiped before every choice ([brain.md](brain.md), "Memory").

`--held-out` plays seed 2,000,000 instead: worlds kept for promotion, which nothing gets tuned on.

`random` is the stand-in brain from 0.1, and the baseline every trained brain has to beat. `greedy` is scripted: it heads for the nearest food any ray sees, and otherwise goes straight and turns away from anything close ahead. It's not a brain and never trains anything. It shows what the senses make possible, so if a trained brain can't get near it, the brain is the problem, not the rays.

From 0.3 greedy also eats what it carries once it can without waste, and `carrier` is greedy that takes its crop home and unloads it once it's full, and goes home to eat when it's hungry and the store has jelly. From 0.4 `chaser` is carrier that runs for any open flower it sees, and `spotter` is chaser that knows where flowers open (the world's spots, in `spots.toml`) and waits at the nearest one when there's nothing to eat or run for in view. Spotter knows the spots without having to see a flower first, so it's the most remembering them could be worth to a scripted forager, and chaser to spotter is what knowing them adds. For the maze nursery, `wall` keeps a wall on its left and goes for any berry it sees (the strategy that needs no memory), and `mapped` knows the maze and where the berry is and takes the shortest way, room by room: about the most any searcher could find. Results also have **stored**, food unloaded into the creature's own store. Food per minute counts food picked up where it grew, eaten or carried. Since a full Terrikin with a full crop can't take any more, 0.3's numbers can't be compared with 0.2's: the 0.2 brain scores 5.23 solo in the 0.3 world against 18.40 in its own. The numbers and how they changed are in [notes/0.3.md](notes/0.3.md).

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
