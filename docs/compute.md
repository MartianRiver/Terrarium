# Compute: the job queue and donated machines

Training runs are queued as jobs. A coordinator holds the queue, and workers (my Mac, other machines of mine, rented GPUs, and anyone who wants to lend a machine) take jobs from it, train, and send the run back. This page says how it works and, since you might run a worker, exactly what a worker will and won't do on your machine.

Three programs, all in `sim/terrarium/`:

| | |
|---|---|
| `jobs.py` | what a job is, signing, and the command line I add batches with and bring finished runs home with |
| `coordinator.py` + `store.py` | the queue: holds jobs and files, hands them out, takes results back |
| `worker.py` + `snapshot.py` | takes a job, checks it, builds its code, trains, uploads the run |
| `machine.py` | the rules a worker keeps on a lent machine so it stays out of the owner's way |

## What a worker will and won't do

The short version: the coordinator can't make a worker run anything. All it can do is relay a job I signed, and a worker checks everything about that job itself before it runs. A worker without `--trusted` (any machine that isn't mine) only ever runs code that's already public on one of this repo's branches.

Before a job runs, the worker checks, in this order:

1. **The job's shape.** Every field is checked (`jobs.check`): ids and names are short plain strings, every input is named by a sha256, and nothing is a path the coordinator chose.
2. **My signature.** Each job is signed on my machine with an ssh key (`ssh-keygen -Y sign`, namespace `terrarium-job`). The worker verifies it against `sim/allowed_signers` in *its own* checkout, the copy you can read, not one the server sends. A job anyone else made, or one of mine with a single byte changed, is refused.
3. **Where the code comes from.** A job names a commit. Without `--trusted`, the worker fetches that commit from the public repo itself and runs it only if it's on one of the repo's branches (`snapshot.from_public`). Only I can push branches there. Pull requests don't count: GitHub serves their commits from the same repo, so a commit someone pushed to a fork could otherwise be fetched by its hash. The worker never takes code from the coordinator. Jobs on uncommitted code (an *overlay* of changed files on top of a commit) are refused outright.
4. **Every input against its hash.** World and training configs (TOML, read by the sim's strict loader: unknown or mistyped keys are an error) and the parent brain. Brains load with `torch.load(weights_only=True)`, which reads tensors and refuses pickled code.

Then it runs `uv sync --locked` in that commit's `sim/` (packages pinned by its `uv.lock`, from PyPI and PyTorch's index) and `python -m terrarium.train` with the job's configs. That's the same command I run by hand (`docs/training.md`).

What it never does:

- run a command, script or path the coordinator sends. The API has four calls: claim a job, fetch a file by hash, renew the claim, upload the result (plus give a job back when stopping).
- listen on anything but `127.0.0.1`: its status page and pause/resume are for you, on your machine.
- write outside its home folder (`~/.terrarium/worker`), apart from uv's own cache of the Python and packages it downloads (PyTorch included), or send anything but the run it made. A result is the run folder `train` wrote (`run.json`, `metrics.jsonl`, `evals.json`, checkpoints) plus the signed job: configs, numbers, your OS and CPU, Python and package versions. Paths in it are relative to the job's checkout, so your username isn't in them. The training log stays on your machine.

What you're still trusting:

- **The code on this repo's branches.** The worker runs the training code at the job's commit. That code is public; read it (or have an LLM read it) the same way you'd read this worker.
- **The packages in `uv.lock`**: numpy, pymunk, torch and their dependencies, as pinned.
- **Me, as the signer.** If my signing key were stolen, someone could sign jobs, but a donor worker would still only run code from this repo's branches.

Without `--trusted` the worker also refuses jobs marked trusted, and the coordinator doesn't offer them to donor tokens or let a donor fetch any file that isn't an input of the job it holds right now.

## The other direction

What comes back from a machine I don't own is data from a stranger, and it's handled that way:

- uploads have a size cap, checked before they're read, and the coordinator has a cap on total results
- a result must be a tar.gz of one run folder named for its job; it's unpacked with Python's `data` filter (no absolute paths, no `..`, no links out) by `jobs sync`
- `promote` already refuses scratch runs and commits that aren't on `next`; it doesn't yet re-score a brain itself (below), so until it does, donated runs aren't promoted
- tokens are one per machine, issued by me and stored only as hashes; revoking one cuts that machine off
- each machine's token may make 60 requests a minute (a worker makes a few); past that it gets 429s, and the other machines don't notice

## Running a worker

You need `git`, [uv](https://docs.astral.sh/uv/) and `ssh-keygen` from OpenSSH 8.1 or later, and a token from me. On Windows the worker uses the `ssh-keygen` that comes with Git for Windows, since the one built into Windows 10 may be too old to check signatures. Either way it checks a known signature when it starts, and stops with a message saying why if it can't.

```
git clone https://github.com/MartianRiver/Terrarium.git
cd Terrarium/sim
uv run python -m terrarium.worker --server https://terrarium-jobs.martianriver.com
```

The first time, it asks for the token and saves it as `~/.terrarium/worker/token`. The worker itself doesn't need torch. Each job's checkout gets its own, the CUDA build when `nvidia-smi` works and the CPU one otherwise; on a Mac it's PyPI's build, which trains on the Mac's GPU (Apple silicon and macOS 14 or later only).

While it runs, `uv run python -m terrarium.worker status` (or http://127.0.0.1:5191/status) shows what it's doing and why: `ready`, `waiting` (on battery, in use, a game on the GPU), `working`, or `paused`. `pause`, `resume` and `drain` (finish the current job, then stop) do what they say.

Every minute, working or not, the worker tells the coordinator what the machine is (OS, CPU, cores, memory, and each NVIDIA GPU with its memory) and that same state and reason. That's everything it sends about your machine: no hostname, user name or files. The coordinator keeps only those fields, cut short, and only I can read them. The public board (`/api/board`, shown on the site) has each machine's name, kind (mine, rented or lent), GPU, samples trained, hours, jobs done and the day it was last active. It never shows the state: "waiting" would tell anyone that you're at your computer. What my Mac and rented GPUs trained outside the queue is added from `sim/board.toml`, which `python -m terrarium.compute board` writes from `runs/` and `compute.toml` (rented GPUs by model, and memory where Vast only has the one size), leaving out runs that came through the queue on Atlas; a run counts as a job there. Ctrl-C (or Ctrl-Break, or SIGTERM) hands unfinished jobs back to the queue; that doesn't count against them.

Each job builds a checkout of its commit with its own `.venv` under `~/.terrarium/worker/code/`. It's big with the CUDA build of torch, and it's reused for every job on the same commit. Deleting the folder while the worker is stopped is always safe. The runs your machine made stay in `~/.terrarium/worker/runs/`, oldest deleted first past 2 GB.

`uv run python -m terrarium.watch` (from the same `sim` folder, beside the worker) shows them in the viewer at http://127.0.0.1:5196: the run training now, playing its newest checkpoint and moving on to whatever is newest each time a replay ends, so a fast GPU's checkpoints in between are skipped, and the runs page with its charts. Each replay is recorded by the checkout that trained it, with its own packages, so a job on another branch plays in the world it was trained in; a kept run whose checkout has been deleted plays in your own copy of the code. The viewer's files come from the site (`/at-home/viewer/`, built by `npm run site`) in one bundle, it and each file in it checked against the sha256 in its `files.json`, and kept in `~/.terrarium/worker/viewer/` for when the site can't be reached. `--viewer DIR` uses one built here instead, and `--no-open` doesn't open a browser. Its Play button starts a game as one Terrikin against the brain your machine is training ([training.md](training.md), Playing as one), played in your own copy of the code. Like the worker, it listens only on your own machine.

### Keeping out of your way

On a machine someone uses, the worker keeps to these rules by default (`machine.py`):

- **Only when you're away.** It starts a job after 10 minutes without keyboard or mouse input. When you come back, it pauses the job on the spot (every process of it is suspended) and carries on once you've been away 10 minutes again.
- **Only on mains.** On battery it pauses, the same way.
- **Never while you're playing.** If another program uses more than a fifth of the GPU's 3D engine, or more than 1 GB of its memory, for 10 seconds, the worker stops the job and gives it back to the queue, freeing the GPU. Anything full screen (a game, a presentation) does the same. It reads the counters Task Manager shows, for the NVIDIA GPU only, and leaves out the desktop itself.
- **Half the CPU, at low priority.** On Windows it's a hard cap on the worker and everything it starts (a job object), so a job can't take more however it's written, and a job dies with the worker if the worker crashes. Elsewhere it's the number of threads and processes a job gets, plus `nice`.
- **Not hot.** Above 85 °C on the GPU it pauses until it's 5 degrees cooler.
- **Not for long.** A job paused for 30 minutes goes back to the queue for another machine.
- **Awake while it trains.** A job runs when nobody's at the machine, which is just when it would go to sleep, so while one trains (not while it's paused) the worker asks the system to stay awake: `SetThreadExecutionState` on Windows, `caffeinate` on macOS, `systemd-inhibit` on Linux. The screen still turns off. Once the job ends or is paused, sleep works as you set it.

What a paused job doesn't hold: the CPU. It does keep the memory it had, a little of it on the GPU. Time spent paused is written into the run (`paused`, in seconds) and left out of its hours (`terrarium.compute`).

Change any of it with flags, or in `~/.terrarium/worker/settings.toml` (flags win):

```toml
cooldown = 10      # minutes away before training; 0 trains while you use it too
battery = false    # also on battery
cpu = 0.5          # share of the cores
gpu_temp = 85      # pause above this; 0 for no limit
share_gpu = false  # keep training while other programs use the GPU
suspended = 30     # minutes a job may sit paused before it goes back
keep_gb = 2        # space for the runs this machine made
keep_awake = true  # no sleeping while a job trains
```

| flag | |
|---|---|
| `--cooldown MIN`, `--battery`, `--cpu SHARE`, `--gpu-temp C`, `--share-gpu` | the rules above |
| `--anytime` | none of the rules: for machines nobody uses (rented machines get this with `--instance`) |
| `--slots N` | jobs at once (default 1); the cores are split between them |
| `--rollouts N` | rollout processes per job (default: its share of the cores, up to 8) |
| `--paused` | start without taking jobs |
| `--max-load X` | don't take a job while the 1-minute load average is above X |
| `--trusted` | also run uncommitted code; only for my own machines |

What it can't see: on macOS, other programs on the GPU, its temperature (there's no NVIDIA there) or anything full screen. On Linux, keyboard and mouse (X and Wayland have no one way to ask, so a Linux machine always counts as away; set `--cooldown 0` and pause it yourself, or don't run it on a machine you sit at). Other GPU programs on Linux come from `nvidia-smi pmon`.

### On Windows

Native Windows is the way to run it on a gaming PC: it's the only place the worker can see your games.

1. Install git and uv, in PowerShell:
   ```
   winget install Git.Git
   winget install astral-sh.uv
   ```
   Then open a new terminal so both are on the path: a normal PowerShell, not "Run as administrator", which starts in `C:\Windows\system32` where git can't write (and the worker shouldn't run as administrator anyway).
2. Check `nvidia-smi` prints your GPU. If it doesn't, update the NVIDIA driver.
3. `cd ~`, then clone and start it as above, from `Terrarium\sim`.

Close the window, or press Ctrl-C, to stop it. A job it was running goes back to the queue (closing the window does this through the lease, about five minutes later). The Windows parts (the GPU counters, the CPU cap, idle and full-screen checks) have tests for their logic, but haven't run on a Windows machine yet; the first friend's laptop is that test.

If native Windows won't work, WSL2 with Ubuntu runs the Linux worker, and CUDA works there through the Windows driver. But from inside WSL the worker can't see Windows: not your keyboard, not your games, not full screen. So there, pause it yourself before you play (`uv run python -m terrarium.worker pause`).

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

`parent` is a `.pt` file, `run:<run id>/<checkpoint>` from `runs/`, or `job:<name>` for the final checkpoint of an earlier job in the batch, which then waits for it. `chunk = N` splits a job into pieces of N samples (`name.1`, `name.2`, …), each starting from the last one's final checkpoint and playing its own episodes (seed + 1000 per piece), so a lent machine only ever holds a short job and one that goes away loses little. `job:<name>` then means the last piece. Each piece starts a fresh optimizer, like any run from a parent. `on = "rented"` keeps a job to rented machines (`"trusted"` to my own, `"donor"` to donated ones); without it, any machine allowed to run the job can take it. Which kind a machine is comes from its token, not from anything the worker says. I use it to test on a rented GPU while the Mac sits out. Parent files are sent byte for byte, so the run they came from can still be traced through the meta saved inside.

```
uv run python -m terrarium.jobs add grid.toml     # signs with ~/.ssh/terrarium_jobs_ed25519
uv run python -m terrarium.jobs list
uv run python -m terrarium.jobs sync              # finished runs → runs/
uv run python -m terrarium.jobs cancel ID | retry ID
uv run python -m terrarium.jobs workers           # each machine's specs, state and when it last reported
```

The code is this checkout's HEAD. A dirty tree goes as an overlay (every changed or untracked file under `sim/`, and the deleted ones), so the run trains on exactly what's on disk, comes out as scratch like any dirty run, and can never be promoted. The overlay itself is saved in the run folder as `overlay.tar.gz`, next to `diff.patch`, and `job.json` holds the signed job. A job is trusted (my machines only) when it has an overlay or its commit isn't on a branch pushed to `origin` yet.

## Leases

A worker claims a job for five minutes and renews the claim every minute, through training and the evals at the end. If a worker disappears, its job goes back in the queue when the claim runs out; a job that fails twice stays failed until retried. A job is done when its run has been uploaded, checked job by job. A worker that restarts hands back whatever the queue thought it held.

## Tokens

The queue is closed: every machine has a token I made for its handle, and the handle is its name on the board. Someone offering a machine asks by issue, email or Instagram, and I make the token on the coordinator's admin page (`/api/admin`), which only I can sign in to, with Google: the coordinator checks the account's verified address against a list it's given (`ADMIN_EMAILS`) and keeps nothing about it, not even the address. A token is shown once. A lost one gets a new one and the old one stops working; one that's misused is revoked. The page also lists every machine with what it is (GPU and its memory, CPU, threads, OS, memory), its worker version (so I can tell who's due a `git pull`), what it's doing, and how its jobs ended: done, lost (it went quiet, so its lease ran out), failed or given back (a lent machine does that by design, when its owner comes back). Sign-in uses Google's code flow with PKCE, a state tied to the browser that started it, and a session that lives 12 hours in the coordinator's memory, in a cookie scripts can't read and other sites can't send. Its settings come from the environment: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAILS` and `PUBLIC_URL`. On my Mac, `python -m terrarium.coordinator token NAME --role donor` still works.

## Not built yet

`promote` re-scoring a donated brain on my machine instead of trusting the run's `evals.json`, renting GPUs automatically when the queue is long (with daily, weekly and monthly spend caps), a queue page next to the runs page, and a container for Unraid. The coordinator runs at `terrarium-jobs.martianriver.com`.
