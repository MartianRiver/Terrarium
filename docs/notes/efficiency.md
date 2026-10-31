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

## Assumptions that cost us

- **A new action padded to mean 0, std 1** fired the unload action on half of all training ticks, so crops never survived the walk home. Eight runs stored nothing before it was found (0.3).
- **Arenas in lockstep**: every arena started at dawn, so whole updates were all-day or all-night. Staggered starts fixed it (0.3).
- **Starting from the carried brain.** Forks of the 0.3 brain got worse in every colony test (eat coin, death weight, fresh heads), and fresh brains beat forks in two worlds (0.4). New lines now start fresh, with a fork as the control.
- **A wipe was treated as a step.** The memory update cut a stream at every step where it wasn't carrying notes, and padded every piece to the rollout's length, so a slot that was never born became 128 one-step pieces 128 steps long. Peekaboo and mazes, with one baby an arena that never dies, never showed it; the first colony with room to grow made 44 times the pieces it needed and ran out of memory on every card we rented.
- **Baselines and controls nobody scored against their own claim.** `last_seen`, the perfect-memory baseline, stood still for good once the berry it remembered was gone, so it found 35% in one-look peekaboo instead of 81%, and the memory brains looked better than perfect memory. Wiping a brain's notes before every choice put it somewhere it never trained, which froze maze brains (a third of the distance walked) and made the cost of losing memory look two to three times what a wipe every 3 s shows.
- **One or two seeds on noisy scorers.** Most nursery calls in 0.4 rest on one or two seeds, some scored on 8 arenas × 1 episode.

## Not measured yet

- Rays test every creature against every other, so their cost grows with the square of the headcount: 0.19 ms an arena-tick for 18 Terrikins, 28 ms for 4 colonies of 48 in a 52 m arena. A grid that only tests nearby creatures should make big worlds affordable.
- Worlds with one or two Terrikins an arena run faster on the M3 than on pods. Likely per-step overhead (few samples a step, slower single cores): try 256–1024 arenas a worker, and CPU-only machines.
