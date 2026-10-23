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

The 0.2 brain took the default 20M samples, 52 minutes on the M3. Food per episode was at 50 by 3M samples and within a few percent of its final 55 by 5M, so most of that run was polish.

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

## Promoting a brain

When a stage is done, its brain is promoted from a run on `next`:

```
uv run python -m terrarium.promote runs/<run> --stage 0.2 --backups ~/backups/terrarium
```

It refuses a run that didn't finish, a scratch run, and one whose commit isn't on `next`. A run from a feature branch counts as not on `next`, because the squash merge leaves its commits behind, so the brain to promote is trained again once the code is merged. It also refuses a last checkpoint that has changed since the run, one that doesn't fit today's schema, one that doesn't clearly beat random in the run's `evals.json` ([evals.md](evals.md)), and a stage that already has a brain.

A promoted brain is copied to `brains/<first 12 of its sha256>.pt` in the backups folder, then gets an entry in [`sim/brains.toml`](../sim/brains.toml): its id, parent, commit, run, samples, schema version and its evals next to random's. At release, the same file is attached to the stage's GitHub release, which the entry names.
