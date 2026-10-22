# Roadmap

Each stage is a version: stage N ships as 0.N.0 once it's done and has been through the checks in [docs/releasing.md](docs/releasing.md). The main world is 1.0. Stages build on each other: every stage's brain starts from the one the stage before it promoted, and a new stage isn't finished if it made an old skill worse.

What each mechanic is for is in [VISION.md](VISION.md). This is the order they arrive in, and what has to be true before a stage counts as done.

## 0.0: Visual demo (done)

*Mac, no AI.* A small 3D scene of blobs wobbling around under scripted movement, food, pushable blocks and flashing signal bulbs. The renderer is the window for everything after, and it's driven by the same frame format the sim will write.

## 0.1: Sim core and replays

*Mac.* A headless 2.5D sim with recordings the viewer can play back, and a known speed to plan compute from.

- The sim in Python: creatures, food, blocks, walls and nests on a flat plane, with sliding, collisions and pushing.
- Physics picked by measuring, not guessing: a custom vectorised sim against a 2D engine, on the same scene. Picked pymunk; the numbers are in [docs/physics.md](docs/physics.md).
- Every balance number in a config file.
- **Replay format v1:** a world header plus frames, matching what the viewer already draws, with a format version from the first file. The viewer opens a replay file. The format is in [docs/replays.md](docs/replays.md).
- A small sample replay kept in the repo, so every later version can prove it still plays the old format.
- **The benchmark:** steps per second for 1, 16 and 64 arenas on the M3, written down as the baseline later stages are held to. Kept in [docs/benchmark.md](docs/benchmark.md).
- Checks in CI: the sim's tests, and a replay written by the sim and read by the viewer's loader.

Done when random creatures in the sim replay in 3D, and the speed number is recorded.

## 0.2: Solo forager

*Mac.* One creature, ray vision, energy, common food. Reward: stay alive and fed. The first trained brain.

- The brain: attention over the things it can see, each with a type, so later stages add types instead of reshaping it. Trained with PPO.
- **Run records:** every training run gets its own folder (outside git) with the commit it ran from, the full config, the parent checkpoint and the observation/action schema version. Training won't start with uncommitted changes, so every brain traces back to exact code.
- **Brain lineage:** a small file in the repo naming each stage's promoted brain, its hash, parent, commit, eval scores and where the weights are backed up. Where that is gets decided here.
- Loading a checkpoint checks its schema version and refuses one that doesn't fit, saying why.
- **Evals v1:** fixed seeds and a few numbers (food per minute, time alive), against a random baseline.

Done when the trained blob clearly beats random on the evals, and there's a clip of it hunting for food.

## 0.3: Colony basics

*Mac.* 6–12 creatures, one nest, one shared brain. Carry food home. The reward shifts partly toward the colony's food store.

- Colony ID and body traits as inputs, added so the 0.2 brain still loads.
- The reward blend as a config dial.

Done when creatures stream between food and nest, and a lone creature still forages as well as the 0.2 brain did.

## 0.4: Signals, scent and cooperation

*Mac, maybe RunPod.* Signal patch (free at first), scent marks (cost energy), and rich food that needs two carriers.

Done when pairs team up on heavy food. Watch for signals or trails starting to mean something.

## 0.5: Movable objects

*Mac, then RunPod.* Blocks of varying weight, some needing two creatures.

- Training on RunPod: run records note the machine, and weights come back to the Mac with their lineage entry.

Done when creatures move things for a purpose. Maybe the first barriers.

## 0.6: Rivals and conflict

*RunPod.* Two colonies, then three or four. Shove and steal first, then attack, health and death. Friendly fire ramped in.

- Self-play against a pool of past brains, drawn from the lineage.

Done when there's stealing, guarding of food patches, fights and retreats. Possibly warning signals before attacks.

## 0.7: Queen and brood

*RunPod.* A scripted queen, eggs, feeding, hatchlings growing up. Raiding rival brood becomes possible.

Done when there are guards staying home, nurses near the brood, and raids on rival nests.

## 0.8: Farming and seasons

*RunPod.* Seeds, fertile soil, lean seasons.

Done when colonies plant and defend farms, and different colonies settle on different strategies. The big one.

## 0.9: Requeening

*RunPod.* The queen can die, and a colony can raise a new one with food and time.

Done when there are colony crises and comebacks.

## 1.0: The main world

*RunPod or a small always-on server.* One continuous real-time world.

- **World state saved apart from the brains,** versioned, and moved forward to new versions instead of reset.
- Swapping in a new brain without wiping the world.
- The viewer streams the live world as well as playing replays.

Done when it's running and worth checking in on.

## Later

- Day/night cycle
- Castes (different body traits at spawn; the colony chooses what to spawn)
- A small energy cost for colour signalling (more honest signals)
- Disguise and impersonation as a deliberate unlock
- The queen as a thinking agent
- Genetics, inheritance, pairing
- Bee-style dances
- True height: ramps and ledges
