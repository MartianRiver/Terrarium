# Doing more with the same compute

Every change that made training, the sim or the viewer cheaper or faster, with the numbers before and after, and every assumption that turned out to be costing us. Kept as we go, beside the changelog. A gain only counts here once it's measured; ideas that haven't been measured yet are at the bottom.

## Gains

| When | Where | What changed | Before → after | Where the idea came from |
|---|---|---|---|---|
| 0.3 | sim | circle tests in the rays keep x and y apart instead of `einsum` | ~45% faster rays | profiling |
| 0.2 | sim | the food-touch test splits x and y (numpy sums over a length-2 axis slowly) | 50% faster at 64 arenas | profiling |
| 0.2 | pods | torch threads capped at the container's CPU quota (pods report the host's 255 cores) | a 30 s bench took 10+ min → 30 s | a pod that ran 20× slow |
| 2026-10-24 | pods | evals cap their threads the same way | two evals at 19+ min each → ~2 min | a PBT pod with 128 cores showing |
| 2026-10-24 | pods | a watcher destroys each pod as its last run finishes | half of a grid's $0.56 was two A10s sitting idle | the bill |
| 2026-10-25 | training | `--fast`: compile + bf16 in the update | 47 → 24.6 ms a minibatch on a 3060 | the update was GPU-bound on small attention kernels |
| 2026-10-25 | training | `--gpu-collect`: workers only step worlds, one batched brain pass a step on the GPU | 13.3k → 24.5k samples/s on a 3080 | a wide brain on the CPU was most of a rollout |
| 2026-10-25 | training | end evals run side by side in processes, on the GPU | 680 → 416 s | waiting for evals at the end of every run |
| 2026-10-29 | rented | RunPod's community 3070 for small worlds | ≈ 320M samples a US$ (11.7k samples/s at US$0.13/h) | trying a second provider |
| 2026-10-30 | viewer | the action camera on critically damped springs | jerk 0.58 → 0.12 px (tag), 2.00 → 0.13 (hide-and-seek) | it looked jittery to watch |
| 2026-10-30 | training | a memory brain's update writes its notes in one GRU call per rollout (cut at wipes) instead of a tick at a time | 512 streams × 128 steps, forward + backward: 248 → 153 ms on the M3's CPU, 168 → 75 ms on its GPU | memory runs spent 66–77% of each round in the update |
| 2026-10-30 | training | a memory brain's update leaves out steps that aren't alive (the dead, the unborn): no GRU piece of their own, no pass through the senses | in colony-young, 6,288 GRU pieces a rollout → 144 (32 arenas × 128 steps, fresh colonies); one minibatch forward + backward 1,215 → 603 ms on the M3's GPU, memory held 4.7 → 2.0 GB. On pods, a colony memory run's GPU memory went from 22 GB on a 3090 (then out of memory) to 2.8 GB, so it runs on a US$0.088/h 3060 at 8k samples/s (330M samples a US$, alone on the card) where it had needed a US$0.216/h 3090 for 12k (200M a US$) and still crashed | every colony memory run of the night crashed, on 12, 16 and 24 GB cards |
| 2026-11-01 | pods | a pod's copy of the repo is a plain clone with its own git objects, built by one script and checked before renting | two pairs of pods died at start (a worktree's `.git` and a `clone --shared` both point back at the laptop): US$0.06 and an hour of the line | runs that said "all done" in two minutes |
| 2026-11-02 | training | the brain's last attention layer works out only the self token, the one its heads read, against all the others, instead of all 17 tokens | picking actions on one core: 3.60 → 2.15 ms for 64 babies at width 64 (×1.68), ×1.5–1.7 across widths 64/128 and 64–256 babies; the same answers to within 1e-6, old brains unchanged | a scan of the code for work thrown away (the encoder's other 16 outputs were dropped) |

## Which card

Samples a US$ on Vast, 2026-10-30, the same bench on each card (two memory peekaboo runs, a colony run without memory, packed on one pod; the colony memory run that should have been the fourth ran out of memory everywhere before the fix above), one host each, steady state past the first updates:

| card | US$/h | samples/s, all runs | million samples a US$ |
|---|---|---|---|
| RTX A4000 | 0.110 | 30.2k | 987 |
| RTX 4080S | 0.234 | 51.4k | 790 |
| RTX 3080 Ti | 0.170 | 33.9k | 717 |
| RTX 3060 | 0.088 | 17.4k | 714 |
| RTX 3090 | 0.216 | 38.3k | 638 |
| RTX 4060 Ti | 0.189 | 29.7k | 565 |
| RTX 3070 | 0.104 | 15.8k (one run left; the others ran out of its 8 GB) | 549 |
| RTX 4090 | 0.402 | 32.1k | 288 |

The dearest card is the worst buy by far, and the same colony run went 3× faster on one 3060's host than another's: the host's CPU matters as much as the card. Picking hosts by measured samples a dollar rather than by price is still to build.

It happened again on 2026-10-31 with three tag runs side by side (no memory, `--gpu-collect`, 4 workers each): a 3080 with 20 cores at US$0.109/h made 17.4k samples/s, 575M a US$; a 3060 at US$0.081/h made 8.6k, 382M a US$, about half the 3060 above. The cheaper pod cost half as much again per sample, and its runs didn't finish in the time it was rented for.

## Which host

The same card trains the same world anywhere from 1.2 to 12 times faster depending on the host. Since 2026-11-01 every pod runs the same test before training (about a minute, in the pod tools): one core's Python speed, a round trip to six worker processes, a small batch through a little net on the card and back, then the tidy nursery's collect as our lines run it, alone and packed. Two hosts the same night:

| | i7-13700 + RTX A4000, Japan | EPYC 7702 (an eighth of it) + RTX 4060 Ti, Quebec |
|---|---|---|
| US$/h | 0.088 | 0.161 |
| one core (Python, M ops/s) | 22.6 | 6.5 |
| round trip to 6 workers | 112 µs | 339 µs |
| small step on the card and back | 0.054 ms | 2.3 ms |
| the host's load (other tenants) | 1.7 | 14.2 |
| tidy collect, one run, `--gpu-collect` | 31.7k samples/s | 8.0k |
| tidy collect, 4 runs packed, all of them | 53.4k | |
| real tidy runs, 2 packed, `--gpu-collect`, each | 14.1k | 5.5k |
| real tidy runs, 2 packed, CPU collect, each | 15.9k | 9.35k |

What sorts hosts is the CPU the training process gets: each step the brain makes a few hundred small calls to the card, and every one costs CPU time to launch, more on a busy shared machine. The card itself hardly matters for the nursery.

On the Mac, letting each worker choose its own actions on the CPU collected the nursery 3.4× faster than `--gpu-collect` (20.2k against 5.9k samples/s), but on CUDA the two were close (34.7k against 31.7k alone), and packed four to a 16-core pod `--gpu-collect` made 53.4k against 37.8k, since its workers only step worlds and leave cores free. Apple's GPU is slow to sample actions for 64 babies a step (3.2 ms of a 9.5 ms step), so the Mac collects small worlds on its CPU. On pods it depends on how many runs share the cores: two runs of six workers on 16 cores, the real runs collected faster on the CPU on both hosts (15.9k against 14.1k a run on the i7, 9.35k against 5.5k on the EPYC, where each small step on the card costs 40 times as much); four runs packed, 24 workers on 16 cores, the CPU runs out and `--gpu-collect` wins. So: CPU collect while the workers fit the cores, `--gpu-collect` past that. Both learned the same: droppings taken out at 4.2M, 47.9, 46.2 and 45.6 with `--gpu-collect`, 49.1, 47.2 and 42.8 on the CPU.

RunPod rents a slice of the vCPUs on a big shared server. On 2026-11-02 none of its community-cloud cards under US$0.25/h were in stock at night, and the one we tried on its other cloud (an RTX 4000 Ada at US$0.28/h) came on a 1.5 GHz EPYC 7702 with a load of 25: 7.3k samples/s in the tidy test and 5.0k a run for two real runs, about a fifteenth of the samples a dollar the i7 above gives. It bills no bandwidth, and its bill matched its hourly rate to the cent, so it would be worth it on a community host with a fast CPU; the pod tools check for one in a couple of minutes.

## Assumptions that cost us

- **A new action padded to mean 0, std 1** fired the unload action on half of all training ticks, so crops never survived the walk home. Eight runs stored nothing before it was found (0.3).
- **Arenas in lockstep**: every arena started at dawn, so whole updates were all-day or all-night. Staggered starts fixed it (0.3).
- **Starting from the carried brain.** Forks of the 0.3 brain got worse in every colony test (eat coin, death weight, fresh heads), and fresh brains beat forks in two worlds (0.4). New lines now start fresh, with a fork as the control.
- **A wipe was treated as a step.** The memory update cut a stream at every step where it wasn't carrying notes, and padded every piece to the rollout's length, so a slot that was never born became 128 one-step pieces 128 steps long. Peekaboo and mazes, with one baby an arena that never dies, never showed it; the first colony with room to grow made 44 times the pieces it needed and ran out of memory on every card we rented.
- **Baselines and controls nobody scored against their own claim.** `last_seen`, the perfect-memory baseline, stood still for good once the berry it remembered was gone, so it found 35% in one-look peekaboo instead of 81%, and the memory brains looked better than perfect memory. Wiping a brain's notes before every choice put it somewhere it never trained, which froze maze brains (a third of the distance walked) and made the cost of losing memory look two to three times what a wipe every 3 s shows.
- **Packing runs on a card by its cores, not its memory** (2026-11-01). A young-colony run takes about 2.6 GB of the GPU and a capture-the-flag run at 256 arenas up to 7 GB, with 1.5–3 GB spikes in the update. Five on a 10 GB 3080, four flag runs on 8, 16 and 24 GB: out of memory each time, four pods and an hour of the night lost (about US$0.10). The dry run on the Mac measures only the CPU's peak. Training's end-of-run evals also run out of memory when the runs still share the card.
- **More arenas a rollout is free speed** (2026-11-01). 256 tidy arenas collect about ×2.75 the samples a second of 64, but each sample teaches less: 24–28 taken out at 4.2M against 43–49, and 49.4 only at 12M, about three times the samples. The updates, not the samples, seem to set the pace. 128 arenas nearly matched 64 (45.5, one seed). 0.4 notes, "More arenas a rollout".
- **Every Vast host is as good as its listing.** Of 26 rentals on one night, nine never got ssh up or never left loading within 10 minutes, and one host failed three times. Each cost a few cents and 5–10 minutes (US$0.20 in all, with the out-of-memory pods); listed reliability of 0.98 meant little, and picking from hosts that had worked before did better.
- **A pod costs its GPU hour.** Every pod downloads 3.8 GB of CUDA torch, and hosts bill downloads at anything from nothing to US$0.039 a GB. On 2026-11-01 three such hosts made downloads US$0.65 of the night's US$1.60: a 10-minute line paid US$0.02 for the card and US$0.15 to download. Over the first 60 days (US$43.40) downloads were 8% of the bill and the disk 7%, and only 67% of all pod dollars paid for time a run was training; the rest went on setup, idle tails and pods that never trained. Offers are now ranked by the samples a dollar we expect with setup and the download paid on top, and hosts dearer than US$0.02 a GB are left out.
- **A CPU's listed clock is its speed.** Vast lists a 2014 Xeon E5-2699 v3 at 3.6 GHz and an EPYC 7702 at 2.0 GHz; the EPYC trained the nursery faster with the same card (29k samples/s a pod against an RTX 4090's 19k on the Xeon). A clock filter would have kept out one of our best hosts. Hosts are now ranked by what they and their CPU model measured before, and every new one runs the same short test first.
- **One or two seeds on noisy scorers.** Most nursery calls in 0.4 rest on one or two seeds, some scored on 8 arenas × 1 episode.

## Not measured yet

Found on 2026-11-02 and measured only in scratch scripts on the M3 (under load from two training runs), so hints until a real line shows them:

- **Where a world step goes, at the sizes training uses.** One tidy nursery step: at 1 arena, pymunk is a small part (0.02 of 0.35 ms); at 64 arenas it's 0.87 of 1.47 ms, and at 256, 4.0 of 4.8 ms, a third to a half of stepping and observing together. Most of it is pymunk's Python wrapper, paid once per arena per step (about 16 µs), not its solver (~12% of the step in the profiler). The rays are already batched over arenas in numpy; what's left there is numpy's per-call overhead. A step also costs ~0.8 ms whatever the number of arenas.
- **Fewer, bigger rollout workers.** Each worker pays that fixed cost on its share of the arenas, so 6 workers of 11 arenas pay it 6 times. Collecting on one core: 4.2k samples/s at 11 arenas a worker, 12.4k at 32, 16.1k at 64. If it holds in real runs, two workers a run collect as fast as six, and a 16-core pod holds 6–8 runs instead of 4. First real runs, on the Mac (M3, 8 cores, CPU collect, tidy nursery, 64 arenas, 1M each, one seed, median of updates): one run at 6 / 3 / 2 / 1 workers made 15.1k / 15.5k / 11.8k / 13.4k samples/s, so one worker gets 89% of six (the dip at 2 is unexplained, maybe where the processes landed on the M3's efficiency cores); two runs side by side at 2 workers each made 15.4k in all against 13.3k at 6 each (×1.16). The update is more than half of each round on the Mac (0.33 s against 0.21 s collecting), so collect gains show less here than on a pod, where the GPU does the update. Next: the same on a 16-core pod (hostbench now has `tidy_cpu2`, 2 workers), and 6–8 packed runs there.
- **The rays in numba** (compiled loops instead of numpy calls): 5–8× faster with the same answers (tidy 0.90 → 0.17 ms at 64 arenas; colony-dung, 24 Terrikins an arena, 59.8 → 9.3 ms).
- **Our own physics, batched over arenas:** a position-based solver in numba stepped 256 nursery arenas in 0.22 ms against pymunk's 4.0 (×18) and colony-sized arenas ×2.8. Position-based solvers lose static friction and mass ratios ("every push eventually moves anything", [physics.md](../physics.md)), so the real one has to be an impulse solver like Box2D's. Together with the rays, collecting an estimated ×2.5; all of training ×1.2–1.6, since the update is the rest.
- **The sim in a browser as it is.** Run through Pyodide (Python built for WebAssembly; pymunk ships wheels for it), a tidy nursery tick took 1.9 ms and a young colony's 5.0 ms, against 50 ms a tick to play at 20 a second, for a ~15.5 MB download. Native and browser runs agree to 1e-15 m in the nursery; in a colony, contacts amplify the last-digit differences until a ray sees something else at tick 337, which matters only for games played in lockstep. So browser play doesn't wait on a new engine; a faster engine is for training.
- **Ramps without 3D:** ramps and ledges as boxes with a height, height levels that only meet their own level (the way a carried thing already floats above the ground), a slope that slows and costs energy. Estimated 2–5% a step; a height map seen by ray-marching cost 41.8 ms a tick for colonies, too slow.
- **Shorter rollouts don't help** (2026-11-02, Mac, tidy 1 m, 4.2M, two seeds each): 64 arenas at 128 / 64 / 32 steps took out 49.3 and 45.5 / 40.7 and 44.6 / 0.0 and 45.9, with one 32-step seed falling apart; 2–4× the updates bought nothing and ran slower (9.9k → 6.9k samples/s). 64 × 128 is the sweet spot for this world (0.4 notes, "More arenas a rollout").
- **Ideas not tried yet:** PPO-EWMA for big batches, value normalisation and a value-only epoch (PPG), double-buffered `--gpu-collect`, CUDA graphs for the small per-step act, Vast's own PyTorch image (cached on many hosts, not billed while loading), interruptible Vast pods at 0.35–0.88× the price once runs resume cleanly, and paired per-arena errors in the evals.

- Rays test every creature against every other, so their cost grows with the square of the headcount: 0.19 ms an arena-tick for 18 Terrikins, 28 ms for 4 colonies of 48 in a 52 m arena. A grid that only tests nearby creatures should make big worlds affordable.
- Worlds with one or two Terrikins an arena run faster on the M3 than on some pods: per-step overhead on slow, shared cores (Which host, above). Still to measure on real lines: 256–1024 arenas a worker, and four runs a pod instead of two.
