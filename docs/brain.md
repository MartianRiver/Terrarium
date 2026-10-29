# The brain

Every creature runs its own copy of the same brain, acting on what it alone senses. It's built so later stages can add senses, kinds of thing and actions without starting over (ROADMAP, "every stage's brain starts from the one the stage before it promoted").

## What it sees

Each creature is one sample, made of tokens:

- **A self token:** energy, forward speed and side speed (as shares of top speed), its last thrust and turn, how full its crop is (as a share of what it holds), whether it's in its own nest, how much jelly its colony has (near 1 at a jelly a member, the way an ant knows how hungry its nest is), how light it is (1 by day, 0 at night, fading at dusk; always 1 without nights), its sprint (the share of a burst left, and how far through the rest after one it is: 1 when it can sprint again, 0 with sprint off), its grip (the share of it left while it holds a block, 0 when it holds none), the smell of food where it stands (0 for faint or none to 1, on a scale of powers of ten) and the sin and cos of the way it gets stronger off the heading (all 0 in worlds without smell), whether it has a berry in its jaws (`load`, 0 without carry), how young it is (`young`, the share of its childhood left: 1 as it hatches, 0 once grown and in worlds without `[young]`), and the way home: the distance to its own nest's centre (in vision ranges) and the sin and cos of its direction off the heading. It may get fuzzier later, so remembering and scent trails have something to do.
- **The nursery games' senses** (all 0 outside their games): whether it's it, in tag; whether it's a seeker and the share of the hiders' head start left, in hide-and-seek; and in capture the flag, whether it carries the other colony's flag, how far that flag is (in vision ranges) and the sin and cos of its direction off the heading, and whether its own colony's flag is taken. Each ray also says whether it ended on a Terrikin that's it, and on one carrying a flag.
- **A token per ray:** what the ray hit (nothing, wall, creature, food, block), how far it got as a share of the range, the sin and cos of its angle off the heading, whether a creature it hit is a nestmate, and how far it got before reaching its own nest and any other colony's.

Rays come from `terrarium.vision`, as many as `[vision] rays` says. Since each ray is its own token, changing the count needs no retraining of the shape, though a brain will see differently with a different fan.

Nests are flat ground, so they don't stop a ray. A ray reports reaching one only if it does so before whatever it hit (a creature in front hides the nest behind it), and the full range when it doesn't. One standing on a nest sees it straight away. Nestmates are a flag rather than a colony number, so one brain works for every colony.

## What it does

- **Thrust and turn,** each in [-1, 1].
- **Unload and eat,** yes when above 0: unload empties the crop where it stands (into a nest's store, or onto the ground outside one), eat takes from the crop once there's room for a whole food, or at home from the store. A brain that hasn't learned them starts leaning no (below).
- **Sprint,** yes when above 0: a burst at 1.6 times top speed for 1.5 s, then 6 s before the next one. Asking once is enough; the burst runs its length. It costs energy by how hard the creature runs during it, so sprinting on the spot is free.
- **Grab,** yes when above 0: takes hold of the nearest block within 15 cm of its body, or the first to come that close, for 2 s from its last yes, and drags it along. It costs a little energy a second while it holds on. It's off (grip 0) in every world but the vault.
- **Carry,** yes when above 0: a yes after a no picks up the nearest berry within 30 cm of its body, or puts down the one it has just in front of it. Holding yes does nothing more, so it takes a fresh yes to change its mind. A carried berry is off the ground (nothing sees or smells it, and nightfall doesn't take it), stays whole, and never goes near the crop: it can't be eaten from the jaws, only put down and then eaten like any other. Carrying slows a Terrikin by 10% and costs 0.002 energy a second. One that dies drops it where it falls. It's on only in the colony world, and nothing pays for it: the question is whether a brain finds a use for it (taking food home for nestmates) on its own. A block marked `carry` in the world config is carried the same way when no berry is in reach, however heavy it is: lifted off the ground (nothing bumps into it, sees it or smells round it), it rides on its carrier, and a fresh yes sets it down crosswise just in front, if the ground there is clear, or it stays carried. The carrying sense says the jaws hold something, berry or block. In `vault-carry.toml` the vault's doors are carried this way, and nothing pushes them.
- **Training samples** from a Gaussian around the brain's mean, with a learned spread, clipped to [-1, 1].
- **Evals take the mean.**
- **Yes/no actions can be coins instead** (`yes_no = "bernoulli"` in the checkpoint; `python -m terrarium.yesno IN OUT` turns one over). Each is then a coin whose odds the brain sets directly, and the world still gets +1 for yes and −1 for no. A Gaussian cut at 0 can push its mean so far down that yes stops being tried; a coin's odds are what training moves. Turned over, a brain keeps about the odds it had (Φ(z) ≈ sigmoid(1.702 z), within 2%), so it acts the same at first; a new coin starts at 5% yes, as a new Gaussian yes/no does. Evals toss coins in `drawn` and `sampled` modes and take the likelier side in `mean`.

## Inside

1. Each ray token is an embedding for its kind plus a linear map of its features; the self token has its own linear map.
2. A 2-layer transformer encoder (width 64, 4 heads, pre-norm) attends over all the tokens.
3. The self token's output gives the mean action and the value estimate.
4. 69,517 weights at width 64 before carry (68,229 in the 0.2 brain, before the crop, the home sense, knowing it's home, the store, the light, the sprint senses, the grip, smell, nests, nestmates, unload, eat, sprint and grab), roughly 300 kB on disk. The 0.3 brain, at width 128, has 270,349, and 270,607 once carry's input and action are added.

## Memory

A brain can carry notes from one choice to the next: a GRU (Cho et al. 2014) after the encoder, which reads the self token's output each choice and updates its notes, and a linear link that reads the notes back into what the heads see. The link starts at zero, so a brain given memory (`train --memory N`) acts exactly as it did without, to the bit, until training finds a use for the notes; a test checks this on a brain with random weights, and the 0.3 brain given 128 notes scores exactly what it did in a short colony eval.

- Each Terrikin's notes start blank when its life does (a new episode, or a hatchling taking a place) and are wiped when it dies.
- What it costs, from the 0.3 brain's 270,349 weights: 32 notes add 19,776 (+7%), 64 add 45,568 (+17%), 128 add 115,584 (+43%), 256 add 329,344 (+122%).
- How far back it learns: PPO replays each creature's choices in order through a whole rollout (`[ppo] steps` choices: 128, which is 12.8 s of world time with each choice held 2 ticks, as the 0.3 brain trained), so what it learns to write down is paid for by what that does within the rollout. The notes themselves carry on across rollouts, so it can remember longer than that, but credit for it has to come through the value estimate.
- `evals --wiped` scores a brain with its notes blanked before every choice. A brain that gains from memory should drop back toward the same brain without it; one that doesn't drop isn't using its notes.
- Widening a brain with memory isn't written yet: widen first, then add memory.

## Sort of on the level of

Each promoted brain gets a `like` in `sim/brains.toml`: the animal it's roughly on the level of, for showing a stage to people. It's a loose ladder, not neuroscience. A weight isn't a synapse, which has timing and chemistry and changes as the animal lives, and an animal's nervous system runs its whole life, not one task. So it compares two things, and says both:

- **wiring:** weights against synapses;
- **what it does:** what the brain has to work with and what it's been trained to do.

| | wiring | what it does |
|---|---|---|
| **0.2 brain** | 68,229 weights | 16 rays and its own energy and speed; no memory from one tick to the next; one drive, eating |
| **0.3 brain** | 270,349 weights (width 128) | rays that tell nestmates, nests, food and flowers apart, smell, the light, its crop, its colony's store and the way home; still no memory; eating, carrying home, getting through the night and hatching |
| C. elegans, a nematode worm | 302 neurons, about 6,400 chemical synapses and 900 gap junctions | its whole nervous system |
| Fruit fly | 139,255 neurons, 5 × 10⁷ synapses | its whole brain |

So the 0.2 brain is about ten times a worm's synapse count and a seven-hundredth of a fly's. It does much less than a worm: wiring on the scale of a worm, doing a small part of what one does.

The 0.3 brain is about forty times a worm's synapse count and a hundred-and-eighty-fifth of a fly's. It does more than the 0.2 brain did, but still less than a worm, and it remembers nothing from one tick to the next.

Sources, checked 2026-10-23:

- WormAtlas, the hermaphrodite nervous system: "elegans hermaphrodite has 302 neurons that belong to two distinct and independent nervous systems", and "The neurons communicate through approximately 6400 chemical synapses, 900 gap junctions, and 1500 neuromuscular junctions".
- Dorkenwald et al., Nature 2024 (FlyWire): "a neuronal wiring diagram of a whole brain containing 5 × 10^7 chemical synapses between 139,255 neurons reconstructed from an adult female Drosophila melanogaster".

Rungs to source before a stage needs them: an ant, a honeybee, a zebrafish larva, a jumping spider.

## Growing it

`sim/terrarium/schema.py` names every self input, ray input, kind and action, in order. The lists only grow, at the end, and `VERSION` goes up when one does.

A checkpoint stores the lists it was trained with:

- **Loading** checks that each saved list is the start of today's. Anything else is refused, naming the list and entry where they part: a renamed input, a reordered kind, or a brain from newer code.
- **A brain from shorter lists loads** with every weight for the new entries set to zero. A new input then has no effect and a new kind looks like nothing at all, until training starts using them. A new action starts as in a fresh brain (std about 0.6), and a yes/no one (unload, eat, sprint, grab, carry) with its mean at −1: it says yes on about 5% of training samples, so it gets tried without wrecking everything else. Evals and replays draw yes/no actions at those odds too, so an untrained one still comes up now and then there, as it did in training ([evals.md](evals.md)). At mean 0 it said yes on half of all samples, and an unload can't be taken back, so a crop never lasted the walk home (docs/notes/0.3.md).
- **A test checks this:** a brain saved with shorter lists gives the same actions and values after loading.

## Checkpoints

A `torch.save` dict, loaded with `weights_only=True`:

| key | what |
|---|---|
| `format` | `terrarium-brain` |
| `schema` | the version and the four lists |
| `shape` | width, layers, heads |
| `weights` | the state dict, on CPU |
| `meta` | where it came from (run, step, parent); written by training |

A brain's id is the sha256 of its file, shown as the first 12 characters.

```
uv run python -m terrarium.evals --config configs/solo.toml --policy random greedy --brain path/to/brain.pt
```
