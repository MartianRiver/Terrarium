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

## Assumptions that cost us

- **A new action padded to mean 0, std 1** fired the unload action on half of all training ticks, so crops never survived the walk home. Eight runs stored nothing before it was found (0.3).
- **Arenas in lockstep**: every arena started at dawn, so whole updates were all-day or all-night. Staggered starts fixed it (0.3).
- **Starting from the carried brain.** Forks of the 0.3 brain got worse in every colony test (eat coin, death weight, fresh heads), and fresh brains beat forks in two worlds (0.4). New lines now start fresh, with a fork as the control.
- **One or two seeds on noisy scorers.** Most nursery calls in 0.4 rest on one or two seeds, some scored on 8 arenas × 1 episode.

## Not measured yet

- Rays test every creature against every other, so their cost grows with the square of the headcount: 0.19 ms an arena-tick for 18 Terrikins, 28 ms for 4 colonies of 48 in a 52 m arena. A grid that only tests nearby creatures should make big worlds affordable.
- Worlds with one or two Terrikins an arena run faster on the M3 than on pods. Likely per-step overhead (few samples a step, slower single cores): try 256–1024 arenas a worker, and CPU-only machines.
