# Training

```
cd sim
uv run python -m terrarium.train solo-first --world configs/solo.toml
```

PPO trains one brain, and every creature runs its own copy of it, CleanRL-style:

1. **Rollouts on the CPU.** `[ppo] arenas` run side by side, each for `steps` ticks per rollout. `--workers N` splits the arenas between N processes. Each worker runs its own copy of the brain on the CPU to choose actions; with `--gpu-collect` the workers only step their worlds, and the brain chooses for all of them at once on `--device`, a step at a time.
2. **Advantages** from GAE.
3. **Updates.** A few clipped passes over each rollout, on CUDA if there is a GPU, else MPS on a Mac, else the CPU. `--device` picks one.

The learning rate falls linearly to zero over `samples`. Every number is in `sim/configs/train.toml`, along with the reward, and the world comes from its own file. The brain is in [brain.md](brain.md).

The 0.2 brain took the default 20M samples, 52 minutes on the M3. Food per episode was at 50 by 3M samples and within a few percent of its final 55 by 5M, so most of that run was polish.

Where it runs and how many workers are facts about the machine, not the training, so they're flags rather than config, and a run on a rented machine doesn't dirty the tree. With one worker the rollouts happen in the training process, seeded as they always were: the same seed gives the same brain. With more, worker i's arenas and sampling are seeded from (seed, i), so a run repeats for the same worker count but not across counts. `--gpu-collect` seeds the worlds the same way, but its actions are drawn from one generator in the training process (on the GPU's own, on CUDA), so its runs don't repeat a CPU-collected one; with one worker and `--device cpu` it plays exactly what the default does, which is how it's tested.

Arenas that end start over at once. With colonies an arena carries on when one creature dies: the dead one's samples are marked inactive and left out of the update until its arena starts over, and each life counts as an episode in the metrics. Dying is an end. Running out of time isn't, since the limit is only there to give training fresh starts and a creature has no clock to see it coming: with `[ppo] bootstrap` on, a creature cut off alive is paid what its value says the rest is worth (Pardo et al., "Time Limits in Reinforcement Learning", 2018). Until 0.3 the cut counted as an end, which cost little while `gamma` looked 5 s ahead, and more once it looked 17 s ahead and things like storing food for the night pay later than that.

A parent brain's actions can be started over with `[start] fresh` in the train config, as new actions start: for one the parent has learned never to take, like `eat` in 0.3. With nights on, `[start] staggered` starts each training arena at a random time of day (and again each time it starts over). Without it every arena starts at dawn together, and since they tend to die out in the same night they stay in step: a rollout is a few seconds of world time, so each update would learn only from day, or only from night. Evals always start at dawn.

`[ppo] repeat` holds each choice for that many ticks and sums the rewards over them, so one sample is one creature making one choice, and `gamma` and `lam` count choices. At 20 Hz with `lam` 0.95, credit reaches about a second ahead; holding choices 4 ticks makes it four times that, and `gamma` 0.999 then looks about 200 s ahead instead of 50. Episode ticks must divide by it. The brain records it and acts the same way in evals and replays. `anneal = false` keeps the learning rate constant instead of falling to 0, for training in chunks that carry on from each other, and `--no-evals` skips the evals at the end when something else scores the run. `--fast` compiles the update and runs the brain's forward pass in bfloat16 (CUDA only; the losses stay float32); it's recorded in run.json.

`--memory N` gives the brain N notes of memory if it has none ([brain.md](brain.md), "Memory"); it acts as before until trained. A brain with memory is updated a whole creature's rollout at a time instead of in shuffled samples: each minibatch is a set of creatures, the part of the brain that looks at the moment runs for all their choices at once, and the notes are then replayed choice by choice from where they stood when the rollout began, wiped wherever they were wiped while collecting (backpropagation through time, as CleanRL's LSTM PPO does it). `--fast` doesn't compile that replay. A test checks the replay gives every living choice the value and log odds it had while collecting, through deaths and fresh episodes. Rivals can't have memory yet.

`--rivals B.pt C.pt` (with `--gpu-collect`) trains several brains in one world, one to a colony: brain k plays colony (k + arena) mod the number of brains, so over the arenas each one takes every seat, and each learns only from its own colonies' samples, at its own `--rival-lr`. The parent is brain 0 and its checkpoints go where they always do; the rivals' go in `rivals/<k>/`, and metrics ending `_k` are brain k's. The first try (notes, "Three brains in one world") made all three worse on their own, so it's there for experiments, not the main line.

## Run records

Each run gets a folder `runs/<date>-<time>-<name>/` at the repo root, outside git:

| file | what |
|---|---|
| `run.json` | id, start and finish, full commit, dirty and scratch flags, both configs in full, parent brain (file, id, and the meta saved in it: the run and samples it came from), schema, brain shape, seed, device, GPU, workers, `fast` and `gpu_collect`, torch threads, machine (platform, CPU, memory), python/numpy/pymunk/torch versions; at the end the samples trained, the last checkpoint's id and its eval numbers |
| `metrics.jsonl` | one line per update: samples, speed, reward, episodes finished with their mean return and length, losses, entropy, KL, clip fraction, explained variance, action spread |
| `checkpoints/` | every `checkpoint_every` updates and at the end, named by samples trained |
| `evals.json` | the last checkpoint and random on the evals ([evals.md](evals.md)) |
| `diff.patch`, `untracked.txt` | only for a run from uncommitted code |

Training refuses to start with uncommitted changes unless it's given `--scratch`. A scratch run is for trying things: it keeps the diff so it can be understood later, and can never be promoted.

`--parent X.pt` carries on from a checkpoint, which has to fit the schema. Its id is recorded as the new brain's parent.

## Speed

On the M3 (4 performance and 4 efficiency cores), one 32k-sample update of the solo world is about 0.9 s of rollout and 3.5 s of update on MPS, so about 8k samples a second, and the update is the limit. A worker's rollout is two thirds the brain choosing actions and one third the sim; shipping a rollout back from a worker takes a few milliseconds. More workers only bring the rollout down to about 0.55 s here, with the efficiency cores and whatever else the Mac is doing in the way, which is why one worker stays the default. They're for machines with a GPU and many cores.

On a rented RTX 3060 with 32 shared EPYC cores ($0.15 an hour), 8 workers and the update on CUDA, the same 20M-sample run took 25 minutes instead of 52, at about 13k samples a second, and learned the same way. Collect stops getting faster past 8 workers there (each EPYC core is about half an M3 core, and other renters share the machine). The update is 1.6 s, and it's the GPU's own time: the brain is small enough that the attention kernels mostly work on padding. `torch.compile` with bf16 halves it on that GPU, but isn't used yet.

That session cost $0.27 for 51 minutes: $0.10 of GPU time, $0.01 of disk, and $0.15 for the 3.9 GB it downloaded, which was mostly CUDA torch, at $0.039 a GB. Bandwidth is priced per host, so it's worth looking at when picking one.

## Training on another machine

```
uv run python -m terrarium.remote start root@HOST -p PORT -- solo --world configs/solo.toml --workers 12
uv run python -m terrarium.remote log root@HOST -p PORT      # the end of the training log
uv run python -m terrarium.remote fetch root@HOST -p PORT    # copy runs/ back here
```

Rented containers often show the host's cores rather than their own share; one pod reported 255 to torch while allowed 30. torch then runs far too many threads, so training caps them at the container's quota (cgroup `cpu.max`) and records the count in `run.json`.

`start` needs a clean tree. It sends the current commit as a git bundle over ssh, installs git, rsync and uv if they're missing, checks the commit out in `~/terrarium`, and starts training in the background, so a dropped connection doesn't stop it. Runs stay in `~/terrarium/runs/` between starts. `fetch` copies them into `runs/` here, where they can be promoted like any other once their commit is on `next`.

On Linux torch comes with an extra: `uv sync --extra cpu`, or `--extra cuda` for an NVIDIA GPU (CUDA 12.6 builds, which need a driver that supports 12.6). PyPI's Linux wheels would bring CUDA whether it's wanted or not. Every `uv run` there needs the same extra, or uv syncs torch away; `start` picks `cuda` when the machine has `nvidia-smi`. macOS takes torch from PyPI, with MPS.

## What it cost

```
uv run python -m terrarium.compute         # hours and dollars per stage, and since the last promotion
uv run python -m terrarium.compute vast    # Vast's charges per instance, checked against compute.toml
```

The hours come from every run in `runs/`: start to finish, or up to its last update for one that was stopped. Scratch runs and abandoned ones count, since they're part of what it took. A run on a rented machine counts once it's fetched.

The dollars come from [`sim/compute.toml`](../sim/compute.toml), one `[[session]]` per rented machine, written when it's destroyed. The bill includes setup, downloads and idle time, so it's more than the training hours at the list price, and the ledger shows each machine's rented hours (start to destroyed) next to its training hours. A session also names the `cpu` and cores it came with, which tells apart pods with the same GPU at the same time. `[[machine]]` entries name my own machines, matched by the CPU and memory their runs record. `compute vast` reads the charges with `VAST_API_KEY` from the environment or `.env`, and says which instances are missing or differ.

Running the Mac isn't counted in dollars.

## Watching a brain

```
uv run python -m terrarium.serve    # in sim/
npm run dev                         # in viewer/, then open /runs.html
```

The runs page lists every run in `runs/`: live, finished, or stopped (no `finished` and nothing written for two minutes). A run's page has its curves (reward per life, seconds alive, samples a second, action spread, KL, explained variance), updating while it trains, and its checkpoints as generations. PPO has no generations of its own, so each checkpoint is one, and random is generation 0 for a run that didn't start from a parent. Watch opens one in the viewer.

Each run's page also says what went into the brain it ends with, per machine: hours and dollars for the run and every run behind its parent, back to the first. A parent that was a checkpoint partway through a run counts up to that checkpoint, and a brain made from another without training (new actions set up, say) is followed through to the one it came from, if its checkpoint's meta names it as `parent`. A rented machine's bill is shared across the runs it hosted by their hours, idle time included; rentals with the same GPU at the same time can only be told apart by their `cpu`, and without one they share their runs. Training hours add up every run, so a pod running three at once shows more training than rented time. The list ends with everything so far per machine, including rentals with no training run on them (evals, probes, failed starts).

The replay is recorded the first time it's asked for, in the run's own world from `run.json` rather than today's config, and kept in the run's `replays/` folder. One takes a second or two. The replay seed picks the arena: the same seed gives every generation the same layout, which is the fair way to compare them. A run on another machine shows up once it's fetched.

### Inside a brain

In a run's replay, click a Terrikin to follow it (a ring marks it, Esc lets go). Each Terrikin has a name, the same every time that episode plays. B opens the brain window on the one followed; it's local only, as it reads the brain through the runs server. The server plays the replay's episode again and writes down what that Terrikin's brain took in and made of it each time it chose (`terrarium/mind.py`, kept in the run's `replays/` folder as `<checkpoint>-<seed>.mind-<id>.jsonl.gz`; about 15 s and 1.5 MB for a 360 s episode). The window shows:

- what it sees: its rays as a fan, in the colour of what each hit, brighter where its attention is; the same rays are drawn on the ground in the world
- where its attention goes: every head of every layer, as its own token's weights over itself and each ray
- what it feels: its senses
- what it makes of it: the units its actions are read from
- how things look: its guess at the reward still to come, over the whole episode
- what it does: push and turn, and the odds of each yes/no with a tick when it said yes

Click any part for what it means. N (or Wired) draws it wired up: senses and rays, its own token's units as it enters and after each layer, and its actions, each unit lit by its value, with the strongest connections into each unit (`/api/runs/<id>/wiring/<checkpoint>`; the feed-forward weights multiplied out, so attention shows as the rays reaching into each layer) glowing by what they carry.

Episodes repeat exactly only on the machine that recorded them: a replay recorded on a pod can part from the same episode played on the Mac, and its mind would then be about another moment. The window checks the mind's positions against the replay and offers to record the replay again here (`?here`).

Or by hand:

```
uv run python -m terrarium.evals --config configs/solo.toml --policy random greedy --brain runs/<run>/checkpoints/<n>.pt
uv run python -m terrarium.record out.jsonl.gz --config configs/solo.toml --seconds 180 --brain runs/<run>/checkpoints/<n>.pt
uv run python -m terrarium.mind mind.jsonl.gz --config configs/solo.toml --brain runs/<run>/checkpoints/<n>.pt --creature 0
```

Open the replay in the viewer.

### Playing as one

Play (or `/?play`, or `/?play=<run id>`) starts a game in a run's world against its newest checkpoint: by default the newest live run, or the newest run if none is training. One Terrikin is yours, with the ring, and every other one is steered by the brain exactly as evals and replays steer it (`terrarium/play.py`, through the runs server's `POST /api/play`). The game moves only when the viewer asks for its next ticks, two at a time with what you're doing in them, so it keeps the viewer's pace and stops when it's paused.

W A S D or the arrows walk and turn; holding the mouse button (or the trackpad) walks you to the spot under the pointer, turning on the spot first if it's behind you. The panel lists only the actions the world has (Shift sprint, Q unload at your nest, E eat, G grab), and right-drag looks around since the left button walks. It scores you the way evals score a brain, food a minute alive and seconds alive, next to the brain's Terrikins. When yours dies its place goes back to the brain (a hatchling there is one of theirs), and you watch to the end; R starts another game. A game plays in the server's own code, so a run whose world or brain that code can't load won't start one.

## Promoting a brain

When a stage is done, its brain is promoted from a run on `next`:

```
uv run python -m terrarium.promote runs/<run> --stage 0.2 --backups ~/backups/terrarium
```

It refuses a run that didn't finish, a scratch run, and one whose commit isn't on `next`. A run from a feature branch counts as not on `next`, because the squash merge leaves its commits behind, so the brain to promote is trained again once the code is merged. It also refuses a last checkpoint that has changed since the run, one that doesn't fit today's schema, one that doesn't clearly beat random in the run's `evals.json` ([evals.md](evals.md)), and a stage that already has a brain.

A promoted brain is copied to `brains/<first 12 of its sha256>.pt` in the backups folder, then gets an entry in [`sim/brains.toml`](../sim/brains.toml): its id, parent, commit, run, samples, schema version and its evals next to random's. At release, the same file is attached to the stage's GitHub release, which the entry names. `--like` adds the animal it's sort of on the level of ([brain.md](brain.md)).

The entry's `compute` says what it took. Every run and rental since the last promotion counts towards this stage, and the totals carry on from the last brain. `lineage_hours` is narrower: the run that made this brain, plus its parents' runs, found in `runs/` or in their own entries.
