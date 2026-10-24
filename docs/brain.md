# The brain

One brain acts for every creature. It's built so later stages can add senses, kinds of thing and actions without starting over (ROADMAP, "every stage's brain starts from the one the stage before it promoted").

## What it sees

Each creature is one sample, made of tokens:

- **A self token:** energy, forward speed and side speed (as shares of top speed), its last thrust and turn, how full its crop is (as a share of what it holds), whether it's in its own nest, and the way home: the distance to its own nest's centre (in vision ranges) and the sin and cos of its direction off the heading. It may get fuzzier later, so remembering and scent trails have something to do.
- **A token per ray:** what the ray hit (nothing, wall, creature, food, block), how far it got as a share of the range, the sin and cos of its angle off the heading, whether a creature it hit is a nestmate, and how far it got before reaching its own nest and any other colony's.

Rays come from `terrarium.vision`, as many as `[vision] rays` says. Since each ray is its own token, changing the count needs no retraining of the shape, though a brain will see differently with a different fan.

Nests are flat ground, so they don't stop a ray. A ray reports reaching one only if it does so before whatever it hit (a creature in front hides the nest behind it), and the full range when it doesn't. One standing on a nest sees it straight away. Nestmates are a flag rather than a colony number, so one brain works for every colony.

## What it does

- **Thrust and turn,** each in [-1, 1].
- **Unload and eat,** yes when above 0: unload empties the crop where it stands (into a nest's store, or onto the ground outside one), eat takes from the crop once there's room for a whole food, or at home from the store. A brain that hasn't learned them starts leaning no (below).
- **Training samples** from a Gaussian around the brain's mean, with a learned spread, clipped to [-1, 1].
- **Evals take the mean.**

## Inside

1. Each ray token is an embedding for its kind plus a linear map of its features; the self token has its own linear map.
2. A 2-layer transformer encoder (width 64, 4 heads, pre-norm) attends over all the tokens.
3. The self token's output gives the mean action and the value estimate.
4. 68,873 weights (68,229 in the 0.2 brain, before the crop, the home sense, knowing it's home, nests, nestmates, unload and eat), roughly 300 kB on disk.

## Sort of on the level of

Each promoted brain gets a `like` in `sim/brains.toml`: the animal it's roughly on the level of, for showing a stage to people. It's a loose ladder, not neuroscience. A weight isn't a synapse, which has timing and chemistry and changes as the animal lives, and an animal's nervous system runs its whole life, not one task. So it compares two things, and says both:

- **wiring:** weights against synapses;
- **what it does:** what the brain has to work with and what it's been trained to do.

| | wiring | what it does |
|---|---|---|
| **0.2 brain** | 68,229 weights | 16 rays and its own energy and speed; no memory from one tick to the next; one drive, eating |
| C. elegans, a nematode worm | 302 neurons, about 6,400 chemical synapses and 900 gap junctions | its whole nervous system |
| Fruit fly | 139,255 neurons, 5 × 10⁷ synapses | its whole brain |

So the 0.2 brain is about ten times a worm's synapse count and a seven-hundredth of a fly's. It does much less than a worm: wiring on the scale of a worm, doing a small part of what one does.

Sources, checked 2026-10-23:

- WormAtlas, the hermaphrodite nervous system: "elegans hermaphrodite has 302 neurons that belong to two distinct and independent nervous systems", and "The neurons communicate through approximately 6400 chemical synapses, 900 gap junctions, and 1500 neuromuscular junctions".
- Dorkenwald et al., Nature 2024 (FlyWire): "a neuronal wiring diagram of a whole brain containing 5 × 10^7 chemical synapses between 139,255 neurons reconstructed from an adult female Drosophila melanogaster".

Rungs to source before a stage needs them: an ant, a honeybee, a zebrafish larva, a jumping spider.

## Growing it

`sim/terrarium/schema.py` names every self input, ray input, kind and action, in order. The lists only grow, at the end, and `VERSION` goes up when one does.

A checkpoint stores the lists it was trained with:

- **Loading** checks that each saved list is the start of today's. Anything else is refused, naming the list and entry where they part: a renamed input, a reordered kind, or a brain from newer code.
- **A brain from shorter lists loads** with every weight for the new entries set to zero. A new input then has no effect and a new kind looks like nothing at all, until training starts using them. A new action starts as in a fresh brain (std about 0.6), and a yes/no one (unload, eat) with its mean at −1: it says yes on about 5% of training samples, so it gets tried without wrecking everything else, and never in evals, which take the mean. At mean 0 it said yes on half of all samples, and an unload can't be taken back, so a crop never lasted the walk home (docs/notes/0.3.md).
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
