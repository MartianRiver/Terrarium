# Compute: the job queue and donated machines

Training runs are queued as jobs. A coordinator holds the queue, and workers (my Mac, other machines of mine, rented GPUs, and anyone who wants to lend a machine) take jobs from it, train, and send the run back. This page says how it works and, since you might run a worker, exactly what a worker will and won't do on your machine.

Three programs, all in `sim/terrarium/`:

| | |
|---|---|
| `jobs.py` | what a job is, signing, and the command line I add batches with and bring finished runs home with |
| `coordinator.py` + `store.py` | the queue: holds jobs and files, hands them out, takes results back |
| `worker.py` + `snapshot.py` | takes a job, checks it, builds its code, trains, uploads the run |
| `trust.py` | what a worker strips out and checks so a lent machine trusts as little as it can |
| `machine.py` | the rules a worker keeps on a lent machine so it stays out of the owner's way |

## What a worker will and won't do

The short version: the coordinator can't make a worker run anything. All it can do is relay a job I signed, and a worker checks everything about that job itself before it runs. A worker without `--trusted` (any machine that isn't mine) only ever runs code that's already public on this repo's `main` or `next`, which only change through a pull request that passed CI.

The longer version matters, though: the training code a job runs is ordinary Python running as you, and nothing in the operating system stops it reading your files. The checks below decide *which* code runs; what you're trusting is that code, and the section after them says exactly what that means.

Before a job runs, the worker checks, in this order:

1. **The job's shape.** Every field is checked (`jobs.check`): ids and names are short plain strings, every input is named by a sha256, and nothing is a path the coordinator chose.
2. **My signature.** Each job is signed with an ssh key (`ssh-keygen -Y sign`, namespace `terrarium-job`). The worker verifies it against `sim/allowed_signers` in *its own* checkout, the copy you can read, not one the server sends. A job anyone else made, or one of mine with a single byte changed, is refused. The first time the worker runs it keeps a copy of `allowed_signers` and shows the keys' fingerprints; if a later `git pull` changes the file, it won't start until you've looked at the change and run it once with `--trust-new-signers`, so who can send your machine jobs never changes without you knowing.
3. **Where the code comes from.** A job names a commit. Without `--trusted`, the worker fetches that commit from the public repo itself and runs it only if it's on `main` or `next` (`snapshot.from_public`). Those two only change through a pull request, in public, once CI has passed; work in progress on other branches never reaches a lent machine. Its copy of the repo holds branches only: GitHub also serves pull requests' commits from the same repo, forks' included, and those never come down. The worker never takes code from the coordinator. Jobs on uncommitted code (an *overlay* of changed files on top of a commit) are refused outright.
4. **Every input against its hash.** World and training configs (TOML, read by the sim's strict loader: unknown or mistyped keys are an error) and the parent brain. A parent named in the job is checked against the hash I signed. A job that carries on from an earlier piece of the same batch (`chunk`) can't name its parent when I sign it, since it doesn't exist yet: that parent is whatever the machine that ran the piece before sent back, checked against the hash the coordinator recorded, so it's data from another machine, not something I signed. Brains load with `torch.load(weights_only=True)`, which reads tensors and refuses pickled code; torch before 2.6 could be tricked into running code that way (CVE-2025-32434), so the worker refuses a commit with an older torch.
5. **Where the packages come from.** Before it installs anything, the worker reads the commit's `uv.lock` and refuses it if any package comes from anywhere but PyPI or PyTorch's own index (a git repo, a URL, a folder).

Then it runs `uv sync --locked` in that commit's `sim/` (packages pinned by its `uv.lock`, each with its hash) and `python -m terrarium.train` with the job's configs. That's the same command I run by hand (`docs/training.md`). Both get only a short list of your environment variables (`PATH`, your home and temp folders, proxy settings and the like; `trust.KEEP_ENV`), never the rest, so tokens or keys you keep in your environment aren't there for them to see.

What it never does:

- run a command, script or path the coordinator sends. The API has four calls: claim a job, fetch a file by hash, renew the claim, upload the result (plus give a job back when stopping).
- listen on anything but `127.0.0.1`: its status page and pause/resume are for you, on your machine. Pause, resume and drain need a header a web page can't send to it without asking first, and a request that arrives under any other host name is turned away, so a website you visit can't flip your worker.
- write outside its home folder (`~/.terrarium/worker`), apart from uv's own cache of the Python and packages it downloads (PyTorch included). That's the worker; the training code it starts could, like any program you run (below).
- send anything but the run it made. A result is the run folder `train` wrote (`run.json`, `metrics.jsonl`, `evals.json`, checkpoints; past the coordinator's 64 MB, every other checkpoint is left out until it fits, never the last, and your copy keeps them all) plus the signed job: configs, numbers, your OS and CPU, Python and package versions. Paths in it are relative to the job's checkout, and its start and finish times are in UTC, so neither your user name nor your time zone is in them. The training log stays on your machine, except when a job fails: then its last 40 lines go to the coordinator so I can see why, with your home folder and user name taken out first.

What you're still trusting:

- **The code on `main` and `next`.** The worker runs the training code at the job's commit as you, with your user's rights: nothing but that code's own good behaviour stops it reading your files or using the network. That code is public, and every change to it went through a pull request; read it (or have an LLM read it) the same way you'd read this worker. If you'd rather not trust it that far, run the worker under a separate user account with nothing of yours in it.
- **The packages in `uv.lock`**: numpy, pymunk, torch and their dependencies, as pinned by version and hash. Pinning isn't auditing: a package that was bad when it was published would be installed as it is.
- **Me, as the signer.** If my signing key were stolen, someone could sign jobs, but a donor worker would still only run code that's on `main` or `next`, and only with configs and brains as inputs.

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

While it runs, `uv run python -m terrarium.worker status` (or http://127.0.0.1:5191/status) shows what it's doing and why: `ready`, `waiting` (on battery, in use, a game on the GPU), `working`, or `paused`. `pause` takes no new jobs and suspends every running one on the spot, the same way as when you come back to the machine (so after 30 minutes paused it goes back to the queue); `resume` carries on once the machine is ready again; `drain` finishes the current job, then stops.

Every minute, working or not, the worker tells the coordinator what the machine is (OS, CPU, cores, memory, and each NVIDIA GPU with its memory) and that same state. A lent machine doesn't send the reason: why it's waiting (someone at it, a game on) stays on it. While a job trains, the report also says how hard the machine is training: samples a second, seconds collecting and updating, how busy the GPU and the cores were in each, and what's holding it back (`terrarium.usage`, [training.md](training.md#where-the-time-goes)), so I can see when a job is set up wrong for your machine. `worker status` shows the same. That's everything it sends about your machine: no hostname, user name or files. The coordinator keeps only those fields, cut short, and only I can read them (the admin page's Training column). The public board (`/api/board`, shown on the site) has each machine's name, kind (its token's role: admin for mine, trusted for people I know, donor for anyone else who asked; or rented), GPU, samples trained, hours, jobs done and the day it was last active. It never shows the state: "waiting" would tell anyone that you're at your computer. What my Mac and rented GPUs trained outside the queue is added from `sim/board.toml`, which `python -m terrarium.compute board` writes from `runs/` and `compute.toml` (rented GPUs by model, and memory where Vast only has the one size), leaving out runs that came through the queue on Atlas; a run counts as a job there. Ctrl-C (or Ctrl-Break, or SIGTERM) hands unfinished jobs back to the queue; that doesn't count against them.

Each job builds a checkout of its commit with its own `.venv` under `~/.terrarium/worker/code/`. It's big with the CUDA build of torch, and it's reused for every job on the same commit; past the three used most recently, older ones are deleted. Deleting the folder while the worker is stopped is always safe. The runs your machine made stay in `~/.terrarium/worker/runs/`, oldest deleted first past 2 GB.

`uv run python -m terrarium.watch` (from the same `sim` folder, beside the worker) shows them in the viewer at http://127.0.0.1:5196: the run training now, playing its newest checkpoint and moving on to whatever is newest each time a replay ends, so a fast GPU's checkpoints in between are skipped, and the runs page with its charts. Each replay is recorded by the checkout that trained it, with its own packages, so a job on another branch plays in the world it was trained in; a kept run whose checkout has been deleted plays in your own copy of the code. The viewer's files come from the site (`/at-home/viewer/`, built by `npm run site`) in one bundle, it and each file in it checked against the sha256 in its `files.json`, and kept in `~/.terrarium/worker/viewer/` for when the site can't be reached. `--viewer DIR` uses one built here instead, and `--no-open` doesn't open a browser. Its Play button starts a game as one Terrikin against the brain your machine is training ([training.md](training.md), Playing as one), played in your own copy of the code. Like the worker, it listens only on your own machine.

### Keeping out of your way

On a machine someone uses, the worker keeps to these rules by default (`machine.py`):

- **Only when you're away.** It starts a job after 10 minutes without keyboard or mouse input. When you come back, it pauses the job on the spot (every process of it is suspended) and carries on once you've been away 10 minutes again.
- **Only on mains.** On battery it pauses, the same way.
- **Never while you're playing.** If another program uses more than a fifth of the GPU's 3D engine, or more than 1 GB of its memory, for 10 seconds, the worker stops the job and gives it back to the queue, freeing the GPU. Anything full screen (a game, a presentation) does the same. It reads the counters Task Manager shows, for the NVIDIA GPU only, and leaves out the desktop itself.
- **Half the CPU, at low priority.** On Windows it's a hard cap on the worker and everything it starts (a job object), so a job can't take more however it's written, and a job dies with the worker if the worker crashes. On Linux the job runs in a systemd scope with a CPU quota, the same kind of hard cap, where there's a user systemd to ask. On macOS it's the number of threads and processes a job gets, plus `nice`, which keeps it to about half but isn't a cap.
- **Not hot.** Above 85 °C on the GPU it pauses until it's 5 degrees cooler.
- **Not for long.** A job paused for 30 minutes goes back to the queue for another machine. A machine that sleeps for more than five minutes (a closed lid) stops checking in, so its job goes back to the queue then, and when it wakes the half-done run is dropped.
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
| `--slots N` | jobs at once; the cores are split between them. Default: what `worker calibrate` found for this machine, else 1 |
| `calibrate` | (a command, like `status`) measures whether this machine gains from two jobs at once; see Slots below |
| `--rollouts N` | rollout processes per job (default: its share of the cores, up to 8) |
| `--paused` | start without taking jobs |
| `--max-load X` | don't take a job while the 1-minute load average is above X |
| `--trusted` | also run uncommitted code; only for my own machines |

What it can't see: on macOS, other programs on the GPU, its temperature (there's no NVIDIA there) or anything full screen. On Linux, keyboard and mouse come from systemd-logind's idle hint for each desktop session, which GNOME and KDE keep: a desktop that isn't marked idle counts as in use, even one whose desktop never sets the hint (then set `--cooldown 0` and pause it yourself), and a machine with no desktop session at all counts as away. Other GPU programs on Linux come from `nvidia-smi pmon`.

### Slots: two jobs at once

One training run leaves the CPU (playing the rollouts) and the GPU (the update) each part idle, so two at once can train more in total than one alone. Measured on my M3, two independent runs gave 1.6 times the samples a second of one. A box that is limited by its CPU's update (the Dell, Alexandria) probably gains nothing, so how many jobs a machine runs is measured for each machine, not guessed.

`uv run python -m terrarium.worker calibrate` (stop the worker first, or let it drain; it refuses while a job is running) trains a fresh brain with 128 notes of memory in `configs/nursery-tree-home.toml` with `configs/train.toml` for about two and a half minutes alone, then two copies for about two and a half minutes at once, each given the cores and rollout processes the worker would give it. It writes the samples a second each way and the most memory held (RAM, and the GPU's on CUDA) to `~/.terrarium/worker/calibration.json` with the date, worker version, torch version and device, and says what it decided: two slots when the pair trains at least 1.2 times as fast as one alone and the two runs peak under 60% of the machine's RAM (under 80% of the card's memory on CUDA), else one. It doesn't follow the keeping-out-of-the-way rules above, since you started it.

It trains a brain with memory in the tree world, not the tiny solo world, because that is what our lines run and a memory brain spends most of its time in updates, which leaves room for a second job: on the Mac, a memory-less brain in `configs/solo.toml` read 1.05 times with two at once (one run alone already fills the machine), where two real memory runs in the tree world gave about 1.5. `--world`, `--train` and `--memory N` (notes for the fresh brain, as in `terrarium.train`) measure something else, such as a line's own configs; the choices are saved in `calibration.json`. The stock `configs/train.toml` (repeat 1, 256 arenas, 4 epochs, no `kl_stop`) isn't the shape of our lines' (repeat 4, 64 arenas, 2 epochs, `kl_stop`), so pass the line's own train file when the answer matters. On a Mac the GPU shares the RAM, so only the RAM figure applies, and it reads each process's resident memory, which can undercount what the GPU holds.

`worker run` without `--slots` uses that file and says in its first log lines which slot count it took and why. With no file it runs one. A file for other hardware (a different GPU, core count, memory, or `--cpu` share) is ignored with a warning (for a different share it names both shares), and one written by an older worker version is used with a warning to calibrate again. It never calibrates by itself. Give `calibrate` the same rules the worker runs with (`--anytime`, `--cpu` or settings.toml): it prints the cpu share it measured at first, since a calibration at another share doesn't count.

Each job in a two-slot machine keeps its own claim, heartbeat, checkout, process and upload, exactly as when it has the machine to itself, and pausing, a game starting or stopping the worker apply to every running job. The worker tells the coordinator its slots with the rest of what it sends (the admin page shows the training speed of one of the jobs). Each run's `job.json` has `beside`: the most other jobs that were training at once while it ran, so real jobs can check the calibration afterwards.

A score job takes the whole machine: it starts only when nothing else is running there, and while it runs the worker claims nothing else. Because the coordinator doesn't know what a worker is already running, a worker that is handed a score job while it has another job gives it straight back (it doesn't count as an attempt) and claims nothing until the machine is empty.

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

`needs` keeps a job to machines that have what it needs, from what each worker says it is: `needs = { gpu = true, gpu_memory_gb = 6 }` for a big brain, `needs = { gpu = false }` for CPU work that should leave the GPUs free, `cores` and `memory_gb` as least amounts, and `machine = "Kelpie"` for one machine by name (a test, or a job only one machine should run). A Mac with Apple silicon counts as having a GPU, its memory shared with the machine's. Unlike `on`, this rests on what the worker reports, so it decides only where a job fits best, never who may run it. A job no machine online can meet waits, and the queue says why (`jobs list` prints it, e.g. "no worker online with gpu = true"). Without `needs`, any machine allowed to run the job can take it. `jobs add` reads each world and train file with this checkout's strict loader before signing, so a file written for older code is refused here rather than on every machine that takes it.

### Score jobs

A job with a `score` table and a `brain` (in place of `train`) plays that brain in its world with `terrarium.games` on whichever machine is free, and comes back as the table (`report.txt`), every game's numbers (`games.json`) and how long it took on what (`score.json`), synced into `runs/scores/`:

```toml
world = "far-32.toml"
train = "train.toml"

[[job]]
name = "far32-s1"
parent = "run:20261105-101500-fs-r4-t1-s2-1a2b3c4d5e6f/00004000000.pt"

[[job]]
name = "far32-s1-score"
brain = "job:far32-s1"
score = { game = "tree-home", episodes = 256, held_out = true, wiped_every = 3.0, baselines = ["picker"] }
```

`brain` takes what `parent` does; `job:<name>` waits for that training job and scores its final brain, so training and its score can go in one batch and the score runs as soon as the brain exists, on another machine. `episodes` defaults to 128 and `baselines` to `["random"]`; `held_out` plays the held-out games, `seed = N` others, and the seed used is written into the job, so two score jobs with the same seed play the same games. `wiped` and `wiped_every` add the brain with its notes blanked, as `terrarium.games` does, and `wiped_on_event = true` adds it with its notes blanked at the game's own event (peekaboo: the berry hiding; the maze: a new room; tree-home: storing an apple in the nest), as `--wiped-on-event` does; a game with no event refuses it when the batch is added. A worker before version 13 would drop that key and score with the notes kept, so it isn't given such a job.

Every game runs on the CPU, one thread a process, so it's the same games on any machine; a score job takes the whole machine (see Slots, above); whether two machines give exactly the same numbers for one brain is checked on the first real ones (a Mac and a Windows box), not assumed. A score job goes first to a machine without a GPU, and a machine with one takes training first and scores only when no training job fits it, so neither kind waits behind the other. Pods, paid by the hour for the GPU, never take a score job unless it says `on = "rented"`. A worker before version 10 doesn't know score jobs and isn't given them. A score job can't be another job's parent: it makes no brain. A score job is always trusted, so only my own machines and rented ones run it, never a donor's: a score is what decides what goes on, and a donated machine could send back any numbers it liked. The rule is in the signed spec, so the coordinator and every worker hold to it.

```
uv run python -m terrarium.jobs add grid.toml     # signs with ~/.ssh/terrarium_jobs_ed25519
uv run python -m terrarium.jobs list
uv run python -m terrarium.jobs sync              # finished runs → runs/, scores → runs/scores/
uv run python -m terrarium.jobs cancel ID | retry ID
uv run python -m terrarium.jobs workers           # each machine's specs, state and when it last reported
```

The code is this checkout's HEAD. A dirty tree goes as an overlay (every changed or untracked file under `sim/`, and the deleted ones), so the run trains on exactly what's on disk, comes out as scratch like any dirty run, and can never be promoted. The overlay itself is saved in the run folder as `overlay.tar.gz`, next to `diff.patch`, and `job.json` holds the signed job. A job is trusted (my machines only) when it has an overlay or its commit isn't on a branch pushed to `origin` yet.

## Leases

A worker claims a job for five minutes and renews the claim every minute, through training and the evals at the end. If a worker disappears, its job goes back in the queue when the claim runs out; a job that fails twice stays failed until retried. A failure says what kind it was: `stuck` or `give_up` when training's own guards ended a collapsing seed (that fails the job at once, since another try with the same seed would only do it again), `crash` when training exited with an error, `setup` when the job couldn't be got ready (the code, its packages, its inputs), and `quiet` when the claim ran out. A job is done when its run has been uploaded, checked job by job. A worker that restarts hands back whatever the queue thought it held.

## Tokens

The queue is closed: every machine has a token I made for its handle, and the handle is its name on the board. Someone offering a machine asks by issue, email or Instagram, and I make the token on the coordinator's admin page (`/api/admin`), which only I can sign in to, with Google: the coordinator checks the account's verified address against a list it's given (`ADMIN_EMAILS`) and keeps nothing about it, not even the address. A token is shown once. A lost one gets a new one and the old one stops working; one that's misused is revoked. The page also lists every machine with what it is (GPU and its memory, CPU, threads, OS, memory), its worker version (so I can tell who's due a `git pull`), what it's doing, and how its jobs ended: done, lost (it went quiet, so its lease ran out), failed or given back (a lent machine does that by design, when its owner comes back). Sign-in uses Google's code flow with PKCE, a state tied to the browser that started it, and a session that lives 12 hours in the coordinator's memory, in a cookie scripts can't read and other sites can't send. Its settings come from the environment: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAILS` and `PUBLIC_URL`. On my Mac, `python -m terrarium.coordinator token NAME --role donor` still works.

## Rented pods

`on = "rented"` jobs can rent their own machines. The pod manager (`terrarium.pods`) runs on a small box of its own, on a bare python with nothing installed, and once a minute:

- asks the coordinator how many `on = "rented"` jobs are waiting and what each of its pods last said, with a token of role `pods`, which can see that and make and revoke its pods' tokens, and nothing else: it can't add, sign, read or cancel jobs;
- rents a pod from the first provider in its list with a card under the price (RunPod: it asks what's in stock first, in the Community and Secure clouds both, and rents the cheapest; the console shows Secure prices, and Community stock for one card comes and goes by the minute), when more jobs wait than its pods can take, while any budget is left: something left of today's share, the week's (Monday on) and the calendar month's, after what pods already running will cost to the end of their hours. Only spend with the providers in its `providers` list counts, so a provider dropped from it stays in the ledger as history but leaves the budget. The budget is soft, so the last pod rented can run over it; today's share is what's left of the week over the week's days left, so a day that ran over leaves the rest of the week a little less. Days start at midnight Sydney time;
- destroys a pod that has failed two jobs without finishing one (a host that can't install the code), and won't rent that Vast machine again for a day; a brain that ended its own run doesn't count, since that says nothing about the host;
- destroys a pod that hasn't said hello within 15 minutes, has gone quiet for 10, has sat 5 minutes with nothing to do and nothing waiting, or has reached its hours. Its token is revoked with it, and any job it held goes back in the queue at once instead of when its lease runs out;
- destroys any pod of its own that its ledger doesn't know (one left over after a crash), and writes down every pod with its price, its machine, what its setup download cost, when it came and went, why, and the commit it ran (SQLite), plus a status file for the box's monitoring.

A pod's setup downloads about 8 GB (uv sync of torch and the CUDA libraries), and Vast bills download per GB on top of the hourly price, at a rate each host sets: at US$0.009 a GB, the first 3060's half hour cost US$0.10 against US$0.03 for its GPU. Vast offers dearer than US$0.003 a GB to download aren't rented, a pod's setup goes into the spend, and a pod keeps taking jobs while there are any, so the download is paid once a pod rather than once a job.

A pod sets itself up from a start script, with no ssh: uv, the commit the manager picked when renting it (the newest on `next`), and the worker with a token of its own that dies after the pod's hours, so a token left on a host doesn't outlive the rental. If the worker ends, or the hours run out, the pod destroys itself with the provider's own key for that one pod (a stopped Vast pod would still bill for its disk). Only pods named `terrarium-q-…` are touched, so pods I rent by hand are left alone.

```
python3 -m terrarium.pods --state DIR --status FILE [--once] [--dry-run]
```

Keys come from systemd's credentials (`coordinator_token`, `vast_api_key`, `runpod_api_key`), never the environment. Settings are `DIR/pods.toml`: `week_usd`, `month_usd`, `zone`, `max_pods`, `max_dph`, `hours`, the GPUs to ask each provider for, and the minutes above; with no file it rents nothing. `--dry-run` decides and logs but rents, destroys and revokes nothing.

## Not built yet

`promote` re-scoring a donated brain on my machine instead of trusting the run's `evals.json`, jobs that add jobs (a population of runs that copies its best, without my Mac), a queue page next to the runs page, and a container for Unraid. The coordinator runs at `terrarium-jobs.martianriver.com`.
