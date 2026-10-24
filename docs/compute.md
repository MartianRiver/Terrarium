# Compute: the job queue and donated machines

Training runs are queued as jobs. A coordinator holds the queue, and workers (my Mac, other machines of mine, rented GPUs, and anyone who wants to lend a machine) take jobs from it, train, and send the run back. This page says how it works and, since you might run a worker, exactly what a worker will and won't do on your machine.

Three programs, all in `sim/terrarium/`:

| | |
|---|---|
| `jobs.py` | what a job is, signing, and the command line I add batches with and bring finished runs home with |
| `coordinator.py` + `store.py` | the queue: holds jobs and files, hands them out, takes results back |
| `worker.py` + `snapshot.py` | takes a job, checks it, builds its code, trains, uploads the run |

## What a worker will and won't do

The short version: the coordinator can't make a worker run anything. All it can do is relay a job I signed, and a worker checks everything about that job itself before it runs. A worker without `--trusted` (any machine that isn't mine) only ever runs code that's already public on this repo's `main` or `next`.

Before a job runs, the worker checks, in this order:

1. **The job's shape.** Every field is checked (`jobs.check`): ids and names are short plain strings, every input is named by a sha256, and nothing is a path the coordinator chose.
2. **My signature.** Each job is signed on my machine with an ssh key (`ssh-keygen -Y sign`, namespace `terrarium-job`). The worker verifies it against `sim/allowed_signers` in *its own* checkout, the copy you can read, not one the server sends. A job anyone else made, or one of mine with a single byte changed, is refused.
3. **Where the code comes from.** A job names a commit. Without `--trusted`, the worker fetches that commit from the public repo itself and runs it only if it's on `main` or `next` (`snapshot.from_public`). It never takes code from the coordinator. Jobs on uncommitted code (an *overlay* of changed files on top of a commit) are refused outright.
4. **Every input against its hash.** World and training configs (TOML, read by the sim's strict loader: unknown or mistyped keys are an error) and the parent brain. Brains load with `torch.load(weights_only=True)`, which reads tensors and refuses pickled code.

Then it runs `uv sync --locked` in that commit's `sim/` (packages pinned by its `uv.lock`, from PyPI and PyTorch's index) and `python -m terrarium.train` with the job's configs. That's the same command I run by hand (`docs/training.md`).

What it never does:

- run a command, script or path the coordinator sends. The API has four calls: claim a job, fetch a file by hash, renew the claim, upload the result (plus give a job back when stopping).
- listen on anything but `127.0.0.1`: its status page and pause/resume are for you, on your machine.
- write outside its home folder (`~/.terrarium/worker`), or send anything but the run it made. A result is the run folder `train` wrote (`run.json`, `metrics.jsonl`, `evals.json`, checkpoints) plus the signed job: configs, numbers, your OS and CPU, Python and package versions. Paths in it are relative to the job's checkout, so your username isn't in them. The training log stays on your machine.

What you're still trusting:

- **The code on `main` and `next`.** The worker runs the training code at the job's commit. That code is public; read it (or have an LLM read it) the same way you'd read this worker.
- **The packages in `uv.lock`**: numpy, pymunk, torch and their dependencies, as pinned.
- **Me, as the signer.** If my signing key were stolen, someone could sign jobs, but a donor worker would still only run code from `main` or `next`.

Without `--trusted` the worker also refuses jobs marked trusted, and the coordinator doesn't offer them to donor tokens or let a donor fetch any file that isn't an input of the job it holds right now.

## The other direction

What comes back from a machine I don't own is data from a stranger, and it's handled that way:

- uploads have a size cap, checked before they're read, and the coordinator has a cap on total results
- a result must be a tar.gz of one run folder named for its job; it's unpacked with Python's `data` filter (no absolute paths, no `..`, no links out) by `jobs sync`
- `promote` already refuses scratch runs and commits that aren't on `next`; it doesn't yet re-score a brain itself (below), so until it does, donated runs aren't promoted
- tokens are one per machine, issued by me and stored only as hashes; revoking one cuts that machine off

## Running a worker

You need `git`, [uv](https://docs.astral.sh/uv/) and `ssh-keygen` (part of OpenSSH; Windows 10 and 11 have it), and a token from me.

```
git clone https://github.com/MartianRiver/Terrarium.git
cd Terrarium/sim
mkdir -p ~/.terrarium/worker && echo YOUR-TOKEN > ~/.terrarium/worker/token
uv run python -m terrarium.worker --server https://terrarium-jobs.martianriver.com
```

| flag | |
|---|---|
| `--slots N` | jobs at once (default 1); the cores are split between them |
| `--rollouts N` | rollout processes per job (default: its share of the cores, up to 8) |
| `--paused` | start without taking jobs |
| `--max-load X` | don't take a job while the 1-minute load average is above X (macOS, Linux) |
| `--trusted` | also run uncommitted code; only for my own machines |

While it runs, `uv run python -m terrarium.worker status` shows what it's doing, and `pause`, `resume` and `drain` (finish the current job, then stop) do what they say. Ctrl-C (or SIGTERM) hands unfinished jobs back to the queue; that doesn't count against them.

Each job builds a checkout of its commit with its own `.venv` under `~/.terrarium/worker/code/`, about 1 GB each with torch. They're reused for every job on the same commit. Deleting the folder while the worker is stopped is always safe.

## Adding jobs

A batch is a TOML file. Top-level keys apply to every `[[job]]`, and each job can override them. Paths are relative to the file.

```toml
world = "world-full.toml"
train = "train-full.toml"
parent = "run:20261024-112747-homing-12m/00012000000.pt"

[[job]]
name = "home1"

[[job]]
name = "home1-seed1"
seed = 1

[[job]]
name = "home1-longer"
parent = "job:home1"
train = "train-full-more.toml"
```

`parent` is a `.pt` file, `run:<run id>/<checkpoint>` from `runs/`, or `job:<name>` for the final checkpoint of an earlier job in the batch, which then waits for it. `on = "rented"` keeps a job to rented machines (`"trusted"` to my own, `"donor"` to donated ones); without it, any machine allowed to run the job can take it. Which kind a machine is comes from its token, not from anything the worker says. I use it to test on a rented GPU while the Mac sits out. Parent files are sent byte for byte, so the run they came from can still be traced through the meta saved inside.

```
uv run python -m terrarium.jobs add grid.toml     # signs with ~/.ssh/terrarium_jobs_ed25519
uv run python -m terrarium.jobs list
uv run python -m terrarium.jobs sync              # finished runs → runs/
uv run python -m terrarium.jobs cancel ID | retry ID
```

The code is this checkout's HEAD. A dirty tree goes as an overlay (every changed or untracked file under `sim/`, and the deleted ones), so the run trains on exactly what's on disk, comes out as scratch like any dirty run, and can never be promoted. The overlay itself is saved in the run folder as `overlay.tar.gz`, next to `diff.patch`, and `job.json` holds the signed job. A job is trusted (my machines only) when it has an overlay or its commit isn't on `origin/main` or `origin/next` yet.

## Leases

A worker claims a job for five minutes and renews the claim every minute, through training and the evals at the end. If a worker disappears, its job goes back in the queue when the claim runs out; a job that fails twice stays failed until retried. A job is done when its run has been uploaded, checked job by job. A worker that restarts hands back whatever the queue thought it held.

## Not built yet

`promote` re-scoring a donated brain on my machine instead of trusting the run's `evals.json`, hosting the coordinator at `terrarium-jobs.martianriver.com`, renting GPUs automatically when the queue is long (with daily, weekly and monthly spend caps), a queue page next to the runs page, and testing on Windows and in a container for Unraid. Until those exist, the coordinator runs on my Mac (`python -m terrarium.coordinator serve --root DIR`).
