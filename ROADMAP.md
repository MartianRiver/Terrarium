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

*Mac and rented GPUs.* Three colonies of six, a nest each, every Terrikin with its own copy of the same brain. Carry food home as jelly, get through the night on it, and race the other colonies for food there isn't enough of.

- New inputs, added so the 0.2 brain still loads: whether a creature a ray hits is from the same colony. A flag rather than a colony number, so one brain works for every colony.
- Nests are something rays can see, own and other. Each creature also knows the distance and direction to its own nest, the way an ant keeps track of the way home. This may get fuzzier in later stages, so remembering and scent trails have something to do.
- The reward blend as a config dial.
- A crop, like an ant's social stomach: food eaten when already full is carried instead, slows the creature down, and is unloaded at the nest as jelly. Being full starts to mean something.
- **The jelly store.** One number per nest in the sim, drawn as a pile that grows. It feeds the colony, but eating jelly gives back less than the food was worth, and only a hungry creature can eat from it. Foraging should always pay better.
- Food grows in patches rather than evenly, since streams only form when food is clumped. Half of it grows in the middle, between the nests, so colonies meet over it.
- **Smell.** Food gives off a smell that spreads and fades, and only part of it gets past a block. A Terrikin senses how strong it is and which way it gets stronger, so it can tell food is that way before it can see any: behind a block, round a wall, or past another Terrikin.
- **Day and night.** Food stops growing at night and what's left standing goes, so the store is what gets a colony through to morning. Nights are cold: energy drains faster, less so in the nest or close to nestmates, so huddling can pay. They can sense the light, and dusk dims slowly, so night can be seen coming. Nights have to be longer than a Terrikin can last on what's in its body, or there's no point keeping a store.
- **Hatching.** Once a colony has lost someone, a store above a threshold pays jelly to hatch a new Terrikin at the nest in its place, full-grown for now. So a store can buy back what the night took.
- Sprint: faster, costs energy, has a cooldown. For getting to food before another colony does, and later for getting out of the way. Turning costs energy too, by how hard, so steering is cheap and spinning on the spot isn't.
- **Scarcity.** Only enough food for about two colonies' worth of Terrikins to live through all three nights of an episode, so colonies race each other for it. With every colony running the same brain, which one makes it is down to place and luck; telling better brains apart comes with rivals in 0.6.
- Foraging is checked in the colony world, not alone. Isolated ant workers die young even with food to hand (Koto et al. 2015), and a colony brain alone turned out the same way, so a lone Terrikin is scored as a number to watch, not held to what the 0.2 brain did.
- **Evals v2:** scripted foragers that carry food home (and one that also goes home at dusk) as the baselines, like greedy was for 0.2. Food stored and eaten, deaths and where they happen (away from the nest by day: a forager that couldn't feed itself), colonies through the night, how often another colony is close when food is eaten, and seeds held back for the release.
- The brain is learned, never copied: forks that train side by side and copy whichever is doing best (population-based training) are how it gets there.

Done when creatures carry food home and store it, colonies get through the night on the store and by huddling, about two colonies in three live through all three nights on food for two, colonies hatch new Terrikins from their store, foragers away from the nest keep themselves fed, and the brain beats the one it started from.

## 0.4 Elderflower: Growth and memory

*Mac and rented GPUs.* A colony that grows and shrinks with what it gathers, and a brain that remembers.

- **Hatchlings.** What hatches starts small and slow instead of full-grown, feeds itself from the store while it's at the nest, and grows into an adult, and a colony can grow past the size it started at, up to a cap. Body traits (size, speed) become inputs, so one brain works for every size. Once that works, passing food mouth to mouth, as ants feed their larvae, gets tried, so nursing can become a job.
- Memory: a few numbers the brain carries from one tick to the next. It forgets food the moment it's out of sight, and getting back to a patch it found needs more than that.
- **Smelling the way home.** The exact sense of where the nest is goes, faded out over training once memory is in. Each nest gives off its colony's scent instead, so close by they can smell home, and further out they have to remember the way.
- Seeing which nestmates are carrying food, the way harvester ants judge how much is out there by who comes home loaded.
- **A brain for each colony.** Each colony's Terrikins learn from their own colony only, with its own reward blend and dials, and the colonies that do best get copied more. Until now every colony has run the same brain, so they couldn't settle on different ways of living.
- **Keeping the nest clean.** Droppings become real: they smell, and they're bad to live beside (how, still to work out), so carrying them away from the nest becomes a job, like an ant colony's waste heap.
- The first danger: a dust devil drifts across the arena, knocking creatures over (they lie still for a moment) and making them drop what they carry. It's weather, not a creature: nothing about it learns.
- Evals: how big each colony gets.

Done when the colony grows from its store and shrinks in lean times, foragers go back to a patch they remember, and creatures keep clear of dust devils.

## 0.5 Foxglove: Working together, moving things

*Mac, then rented GPUs.* Signal patch (free at first), scent marks (cost energy), rich food that needs two carriers, and blocks of varying weight, some needing two creatures.

- Two scent marks, one that draws others and a "no entry" one, as Pharaoh's ants use, laid on the same smell the food has. Both learned: no scripted trail-layers to get them started, even though that makes the first trails harder to find.
- Shivering: spending energy to warm nestmates close by, so huddling can split into heaters and passengers, as it does in honeybees.

- With dust devils about, a signal has more to mean than "help me carry this".
- **Moving blocks on purpose.** Walking into a block isn't enough to move it: a hard push, costing energy, moves it the way the Terrikin is going. Blocks in the way of food first, then heavier ones that need two. In 0.3's tries, light blocks got pushed aside by Terrikins just walking at food, which isn't the same as moving them on purpose, and a grab-and-drag for doors never got learned (notes 0.3).
- Shove: knocks the target back and makes it drop what it's carrying, no damage. Costs energy, has a cooldown. For clearing paths and moving things, and the same knock and drop as the dust devil's.
- The store's hunger limit loosened, so a creature can eat jelly it doesn't need. Nestmates can shove it off: caught in the act, not by reputation. Learning to shove nestmates first means it's already a skill when rivals arrive.

Done when pairs team up on heavy food and heavy blocks, and creatures move things for a purpose. Maybe the first barriers, and freeloaders pushed off the store. Watch for signals or trails starting to mean something, warnings especially.

## 0.6 Gorse: Rivals and conflict

*Rented GPUs.* Two colonies, then three or four. Shoving rivals and stealing first, then attack, health and death. Friendly fire ramped in.

- Rivals can take jelly from a nest's store and carry it home; the colony can push or fight them off.

- Self-play against a pool of past brains, drawn from the lineage.

Done when there's stealing, guarding of food patches, fights and retreats. Possibly warning signals before attacks.

## 0.7 Honeysuckle: Queen and brood

*Rented GPUs.* A scripted queen, eggs, feeding, hatchlings growing up. Raiding rival brood becomes possible.

Done when there are guards staying home, nurses near the brood, and raids on rival nests.

## 0.8 Ivy: Farming and seasons

*Rented GPUs.* Seeds, fertile soil, lean seasons.

Done when colonies plant and defend farms, and different colonies settle on different strategies. The big one.

## 0.9 Juniper: Requeening

*Rented GPUs.* The queen can die, and a colony can raise a new one with food and time.

Done when there are colony crises and comebacks.

## 1.0 Kingcup: The main world

*Rented GPUs or a small always-on server.* One continuous real-time world.

- **World state saved apart from the brains,** versioned, and moved forward to new versions instead of reset.
- Swapping in a new brain without wiping the world.
- The viewer streams the live world as well as playing replays.

Done when it's running and worth checking in on.

## Later

- More to night: shorter sight in the dark, glowing signals easier to spot, night raids
- Castes (different body traits at spawn; the colony chooses what to spawn)
- A small energy cost for colour signalling (more honest signals)
- Disguise and impersonation as a deliberate unlock
- The queen as a thinking agent
- Genetics, inheritance, pairing
- Bee-style dances
- Learning from each other within a life: a trick one Terrikin finds spreading through its colony, as string pulling spread through bumblebees. Needs memory first, and probably more than reward alone.
- True height: ramps and ledges
- Dealing with nestmates that don't pull their weight over time, not just when caught in the act. Needs telling individuals apart, and longer memory.

## Walking

A separate track, after the colony stages. In the sim a creature slides on a plane, and the waddle is only the viewer's. Here it gets a real body with legs in 3D physics, and a small body brain learns to walk, taking the colony brain's thrust and turn as what it's asked to do. Knocked over (from 0.4) becomes something it has to get up from. It's the step towards a real robot. It learns to walk from rewards and costs alone, never from recordings of how real animals move.

## Lab

A long-running track beside the stages: arenas copied from the classic bee and ant experiments, used to measure how close the Terrikins get to the real thing. Each one is set up from the original paper, and scored the same way the researchers scored the insects.

- **Bees:** counting, putting zero below one, telling same from different, visiting several flowers in a good order, finding the way home by the sun, and dances that say where food is.
- **Ants:** the double bridge (do they settle on the shorter way?), bridging a gap with their own bodies, choosing between two nest sites, and leading a nestmate to food.

Some of these the Terrikins may never do, and that's part of what it measures. The long-term goals behind it are real navigation, colonies with their own traditions that outlast the Terrikins who started them, and a colony that solves problems none of its members could alone, the way an ant colony works as one "liquid brain".
