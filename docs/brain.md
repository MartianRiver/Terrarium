# The brain

One brain acts for every creature. It's built so later stages can add senses, kinds of thing and actions without starting over (ROADMAP, "every stage's brain starts from the one the stage before it promoted").

## What it sees

Each creature is one sample, made of tokens:

- **A self token:** energy, forward speed and side speed (as shares of top speed), and its last thrust and turn.
- **A token per ray:** what the ray hit (nothing, wall, creature, food, block), how far it got as a share of the range, and the sin and cos of its angle off the heading.

Rays come from `terrarium.vision`, as many as `[vision] rays` says. Since each ray is its own token, changing the count needs no retraining of the shape, though a brain will see differently with a different fan.

## What it does

- **Thrust and turn,** each in [-1, 1].
- **Training samples** from a Gaussian around the brain's mean, with a learned spread, clipped to [-1, 1].
- **Evals take the mean.**

## Inside

1. Each ray token is an embedding for its kind plus a linear map of its features; the self token has its own linear map.
2. A 2-layer transformer encoder (width 64, 4 heads, pre-norm) attends over all the tokens.
3. The self token's output gives the mean action and the value estimate.
4. About 70k parameters, roughly 300 kB on disk.

## Growing it

`sim/terrarium/schema.py` names every self input, ray input, kind and action, in order. The lists only grow, at the end, and `VERSION` goes up when one does.

A checkpoint stores the lists it was trained with:

- **Loading** checks that each saved list is the start of today's. Anything else is refused, naming the list and entry where they part: a renamed input, a reordered kind, or a brain from newer code.
- **A brain from shorter lists loads** with every weight for the new entries set to zero. A new input then has no effect, a new kind looks like nothing at all, and a new action's mean is 0, until training starts using them.
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
