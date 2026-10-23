# Roadmap

Each stage is a version: stage N ships as 0.N.0 once it's done and has been through the checks in [docs/releasing.md](docs/releasing.md). The main world is 1.0. Stages build on each other: every stage's brain starts from the one the stage before it promoted, and a new stage isn't finished if it made an old skill worse.

What each mechanic is for is in [VISION.md](VISION.md). This is the order they arrive in, and what has to be true before a stage counts as done.

Each stage has a codename, a garden plant, going through the alphabet from Acorn at 0.0 to Kingcup at 1.0. The creatures are Terrikins.

## 0.0 Acorn: Visual demo (done)

*Mac, no AI.* A small 3D scene of blobs wobbling around under scripted movement, food, pushable blocks and flashing signal bulbs. The renderer is the window for everything after, and it's driven by the same frame format the sim will write.

## 0.1 Bulb: Sim core and replays (done)

*Mac.* A headless 2.5D sim with recordings the viewer can play back, and a known speed to plan compute from.

- The sim in Python: creatures, food, blocks, walls and nests on a flat plane, with sliding, collisions and pushing.
- Physics picked by measuring, not guessing: a custom vectorised sim against a 2D engine, on the same scene. Picked pymunk; the numbers are in [docs/physics.md](docs/physics.md).
- Every balance number in a config file.
- **Replay format v1:** a world header plus frames, matching what the viewer already draws, with a format version from the first file. The viewer opens a replay file. The format is in [docs/replays.md](docs/replays.md).
- A small sample replay kept in the repo, so every later version can prove it still plays the old format.
- **The benchmark:** steps per second for 1, 16 and 64 arenas on the M3, written down as the baseline later stages are held to. Kept in [docs/benchmark.md](docs/benchmark.md).
- Checks in CI: the sim's tests, and a replay written by the sim and read by the viewer's loader.

Done when random creatures in the sim replay in 3D, and the speed number is recorded.

## 0.2 Clover: Solo forager (done)

*Mac.* One creature, ray vision, energy, common food. Reward: stay alive and fed. The first trained brain.

- The brain: attention over the things it can see, each with a type, so later stages add types instead of reshaping it. Trained with PPO.
- **Run records:** every training run gets its own folder (outside git) with the commit it ran from, the full config, the parent checkpoint and the observation/action schema version. Uncommitted changes only train as a scratch run, and only runs from committed code can be promoted, so every brain that matters traces back to exact code.
- **Brain lineage:** a small file in the repo naming each stage's promoted brain, its hash, parent, commit, eval scores and where the weights are backed up: on the stage's GitHub release, with a copy in a local backups folder.
- Loading a checkpoint checks its schema version and refuses one that doesn't fit, saying why.
- **Evals v1:** fixed seeds and a few numbers (food per minute, time alive), against a random baseline.

Done when the trained blob clearly beats random on the evals, and there's a clip of it hunting for food. The promoted brain eats 18.4 food a minute and lives every episode out, against random's 0.26 and 50 s ([docs/evals.md](docs/evals.md)).

## 0.3 Daisy: Colony basics

*Mac.* 6–12 creatures, one nest, one shared brain. Carry food home as jelly. The reward shifts partly toward the colony's store.

- New inputs, added so the 0.2 brain still loads: body traits (size, speed), and whether a creature a ray hits is from the same colony. A flag rather than a colony number, so one brain works for every colony.
- Nests are something rays can see, own and other. Each creature also knows the distance and direction to its own nest, the way an ant keeps track of the way home. This may get fuzzier in later stages, so remembering and scent trails have something to do.
- The reward blend as a config dial.
- A crop, like an ant's social stomach: food eaten when already full is carried instead, slows the creature down, and is unloaded at the nest as jelly. Being full starts to mean something.
- **The jelly store.** One number per nest in the sim, drawn as a pile that grows. Above a threshold it hatches a new Terrikin, up to a cap: a hatchling is small and slow, feeds itself from the store while it's at the nest, and grows into an adult. Below the threshold the store feeds the colony, but eating jelly gives back less than the food was worth and takes from the colony's share of the reward, and at first only a hungry creature can eat from it at all. Foraging should always pay better.
- Memory: a few numbers the brain carries from one tick to the next. The 0.2 brain forgets food the moment it's out of sight, and getting back to a patch it found needs more than that.
- Food grows in patches rather than evenly, since streams only form when food is clumped.
- Trained on a mix of colony arenas and solo ones, so the 0.2 skill isn't lost.
- **Evals v2:** a scripted forager that carries food home as the baseline, like greedy was for 0.2. Trips home, how much food is stored rather than eaten, and how big the colony gets.

Done when creatures stream between food and nest, the colony grows from its store, and a lone creature still forages as well as the 0.2 brain did.

## 0.4 Elderflower: Signals, scent and cooperation

*Mac, maybe RunPod.* Signal patch (free at first), scent marks (cost energy), and rich food that needs two carriers. And the first danger: dust devils.

- A dust devil drifts across the arena, knocking creatures over (they lie still for a moment) and making them drop what they carry. It's weather, not a creature: nothing about it learns.
- Sprint: faster, costs energy, has a cooldown. For getting out of the way.
- With something to warn about, a signal has more to mean than "help me carry this".

Done when pairs team up on heavy food, and creatures keep clear of dust devils. Watch for signals or trails starting to mean something, warnings especially.

## 0.5 Foxglove: Movable objects

*Mac, then RunPod.* Blocks of varying weight, some needing two creatures.

- Shove: knocks the target back and makes it drop what it's carrying, no damage. Costs energy, has a cooldown. For clearing paths and moving things, and the same knock and drop as the dust devil's.
- The store's hunger limit loosened, so a creature can eat jelly it doesn't need. Nestmates can shove it off: caught in the act, not by reputation. Learning to shove nestmates first means it's already a skill when rivals arrive.
- Training on RunPod: run records note the machine, and weights come back to the Mac with their lineage entry.

Done when creatures move things for a purpose. Maybe the first barriers, and freeloaders pushed off the store.

## 0.6 Gorse: Rivals and conflict

*RunPod.* Two colonies, then three or four. Shoving rivals and stealing first, then attack, health and death. Friendly fire ramped in.

- Rivals can take jelly from a nest's store and carry it home; the colony can push or fight them off.

- Self-play against a pool of past brains, drawn from the lineage.

Done when there's stealing, guarding of food patches, fights and retreats. Possibly warning signals before attacks.

## 0.7 Honeysuckle: Queen and brood

*RunPod.* A scripted queen, eggs, feeding, hatchlings growing up. Raiding rival brood becomes possible.

Done when there are guards staying home, nurses near the brood, and raids on rival nests.

## 0.8 Ivy: Farming and seasons

*RunPod.* Seeds, fertile soil, lean seasons.

Done when colonies plant and defend farms, and different colonies settle on different strategies. The big one.

## 0.9 Juniper: Requeening

*RunPod.* The queen can die, and a colony can raise a new one with food and time.

Done when there are colony crises and comebacks.

## 1.0 Kingcup: The main world

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
- Dealing with nestmates that don't pull their weight over time, not just when caught in the act. Needs telling individuals apart, and longer memory.

## Walking

A separate track, after the colony stages. In the sim a creature slides on a plane, and the waddle is only the viewer's. Here it gets a real body with legs in 3D physics, and a small body brain learns to walk, taking the colony brain's thrust and turn as what it's asked to do. Knocked over (from 0.4) becomes something it has to get up from. It's the step towards a real robot.
