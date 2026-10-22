# Training

```
cd sim
uv run python -m terrarium.train solo-first --world configs/solo.toml
```

PPO trains one brain for every creature, CleanRL-style:

1. **Rollouts on the CPU.** `[ppo] arenas` run side by side, each for `steps` ticks per rollout.
2. **Advantages** from GAE.
3. **Updates.** A few clipped passes over each rollout, on `[ppo] device` (MPS on the Mac).

The learning rate falls linearly to zero over `samples`. Every number is in `sim/configs/train.toml`, along with the reward, and the world comes from its own file. The brain is in [brain.md](brain.md).

Arenas that end start over at once, and running out of time counts as an end like dying does. Not bootstrapping that cut-off costs nothing here: episodes last minutes, and `gamma` looks a few seconds ahead.

## Run records

Each run gets a folder `runs/<date>-<time>-<name>/` at the repo root, outside git:

| file | what |
|---|---|
| `run.json` | id, start and finish, full commit, dirty and scratch flags, both configs in full, parent brain (file and id), schema, brain shape, seed, machine, python/numpy/pymunk/torch versions; at the end the samples trained, the last checkpoint's id and its eval numbers |
| `metrics.jsonl` | one line per update: samples, speed, reward, episodes finished with their mean return and length, losses, entropy, KL, clip fraction, explained variance, action spread |
| `checkpoints/` | every `checkpoint_every` updates and at the end, named by samples trained |
| `evals.json` | the last checkpoint and random on the evals ([evals.md](evals.md)) |
| `diff.patch`, `untracked.txt` | only for a run from uncommitted code |

Training refuses to start with uncommitted changes unless it's given `--scratch`. A scratch run is for trying things: it keeps the diff so it can be understood later, and can never be promoted.

`--parent X.pt` carries on from a checkpoint, which has to fit the schema. Its id is recorded as the new brain's parent.

## Watching a brain

```
uv run python -m terrarium.evals --config configs/solo.toml --policy random greedy --brain runs/<run>/checkpoints/<n>.pt
uv run python -m terrarium.record out.jsonl.gz --config configs/solo.toml --seconds 180 --brain runs/<run>/checkpoints/<n>.pt
```

Open the replay in the viewer.
