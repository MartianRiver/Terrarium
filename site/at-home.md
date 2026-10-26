---
title: Terrarium at Home
description: Lend a spare NVIDIA GPU to train the Terrikins' brains. What it does on your machine, how to install it, and what lent machines have trained so far.
usd_per_billion: 3.46
rate_from: everything I'd spent on rented GPUs by 26 October 2026, over every sample they trained
aud_per_usd: 1.424
aud_date: 23 October 2026
---

Every brain on this site learned by practice, and practice is samples: one Terrikin taking one step, billions of times over. So far that's been my MacBook Air and GPUs I rent by the hour, which have cost about A$4.93 (US$3.46) for every billion samples. A gaming PC sitting idle most of the day could do the same work.

If you have an NVIDIA GPU that's often idle, you can lend it. A small program, the worker, takes training jobs from my queue while you're away from the computer, sends back the brain it trained, and gets out of the way when you come back. Every machine that does shows up on the board below.

## What it does on your machine

- **Only my jobs, only public code.** Every job is signed by me, and your copy of the code checks the signature, not the server. The code a job runs is fetched from this repo on GitHub, and only if it's on one of its branches, so anything your machine runs, you (or anyone) can read first.
- **Only when you're away.** It starts after 10 minutes without keyboard or mouse, only on mains power, and pauses the moment you're back. A game or anything full screen sends the job back to the queue and frees the GPU.
- **Not all of it.** At most half the CPU, at low priority, and it pauses if the GPU passes 85 °C.
- **Awake while it works.** While a job trains, it keeps the computer from going to sleep, so you don't have to change your power settings. The screen still turns off, and sleep works as normal again once the job is done or paused.
- **Its own folder.** Jobs, their code and their runs live in `~/.terrarium/worker`. The one exception is [uv](https://docs.astral.sh/uv/), which keeps the Python and packages it downloads (PyTorch included) in its own cache. It listens only on your own machine.
- **What it sends.** The runs it trained, and once a minute what your machine is (OS, CPU, cores, memory, NVIDIA GPU) and whether it's working, waiting or paused. No hostname, user name or files. The board shows your machine's name, its GPU and what it's trained, never whether you're at it.

The whole of it, with how to change each rule, is in [docs/compute.md](https://github.com/MartianRiver/Terrarium/blob/HEAD/docs/compute.md).

## Is it safe?

<!-- reviews -->

## Installing it

You'll need a token from me. Open an [issue](https://github.com/MartianRiver/Terrarium/issues), email martianriver@outlook.com or DM me on [Instagram](https://www.instagram.com/martianriver/), and say what GPU you have and the name you'd like on the board.

On Windows, in PowerShell, one line at a time:

```
winget install Git.Git
winget install astral-sh.uv
```

Then open a new PowerShell window (a normal one, not "Run as administrator"), check `nvidia-smi` lists your GPU, and:

```
cd ~
git clone https://github.com/MartianRiver/Terrarium.git
cd Terrarium\sim
uv run python -m terrarium.worker --server https://terrarium-jobs.martianriver.com
```

On macOS or Linux it's the same four lines (`cd Terrarium/sim`), with [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/) installed first. On a Mac there's no NVIDIA GPU, so it trains slowly; Linux can't tell when you're at the keyboard, so pause it yourself before you use it.

The first time, it asks for the token. The first job downloads about 2.5 GB (PyTorch with CUDA) and takes a while to start. Close the window or press Ctrl-C to stop it; a job it was running goes back to the queue. To update it, run `git pull` in the Terrarium folder and start it again.

## Versions

- **5** · 26 October 2026 · Checks when it starts that it can verify my signature, using the `ssh-keygen` that comes with Git on Windows (Windows 10's own may be too old).
- **4** · 26 October 2026 · Keeps the computer awake while a job trains, and cleans up properly when a job is taken away (after a sleep, its leftover processes held the GPU).
- **3** · 26 October 2026 · Says what the machine is and what it's doing every minute, for the board.
- **2** · 25 October 2026 · The rules above that keep it out of your way, Windows included.
- **1** · 24 October 2026 · The first: signed jobs, public code only.

Everything else that changes in Terrarium is in the [changelog](https://github.com/MartianRiver/Terrarium/blob/HEAD/CHANGELOG.md).

## The board

<!-- board -->
