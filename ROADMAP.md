# Roadmap

Each stage is a version: stage N opens as 0.N.0 with its first milestone, and each milestone after it ships as 0.N.y once it has been through the checks in [docs/releasing.md](docs/releasing.md). The main world is 1.0. A stage's recommended brain has to beat the last stage's on the new stage's own world. Starting from the last stage's brain is still the first thing I try, but twice now a fresh brain has done better than one that started from an older brain, so where each brain came from is written down in `brains.toml` instead of being a rule.

What each mechanic is for is in [VISION.md](VISION.md). This is the order they arrive in, and what has to be true before a stage counts as done. From 0.4 on, every milestone's "done when" is small enough to check on its own, and it's met when a finding in [docs/findings](docs/findings/README.md) says so.

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

*Mac and rented GPUs.* Three colonies of six, a nest each, every Terrikin with its own copy of the same brain. Find food, carry it home as jelly, get through the night on it, and grow the colony from what's stored.

- New inputs, added so the 0.2 brain still loads: whether a creature a ray hits is from the same colony. A flag rather than a colony number, so one brain works for every colony.
- Nests are something rays can see, own and other. Each creature also knows the distance and direction to its own nest, the way an ant keeps track of the way home. This may get fuzzier in later stages, so remembering and scent trails have something to do.
- The reward blend as a config dial.
- A crop, like an ant's social stomach: food eaten when already full is carried instead, slows the creature down, and is unloaded at the nest as jelly. Being full starts to mean something.
- **The jelly store.** One number per nest in the sim, drawn as a pile that grows. It feeds the colony, but eating jelly gives back less than the food was worth, and only a hungry creature can eat from it. Foraging should always pay better.
- Food grows in patches rather than evenly, since streams only form when food is clumped. Half of it grows in the middle, between the nests, so colonies meet over it.
- **Smell.** Food gives off a smell that spreads and fades, and only part of it gets past a block. A Terrikin senses how strong it is and which way it gets stronger, so it can tell food is that way before it can see any: behind a block, round a wall, or past another Terrikin.
- **Day and night.** Food stops growing at night and what's left standing goes, so the store is what gets a colony through to morning. Nights are cold: energy drains faster, less so in the nest or close to nestmates, so huddling can pay. They can sense the light, and dusk dims slowly, so night can be seen coming. Nights have to be longer than a Terrikin can last on what's in its body, or there's no point keeping a store.
- **Hatching.** A store above a threshold pays jelly for an egg in the nest, which hatches a new Terrikin, full-grown for now: in the place of one the colony lost, or in room for two more past the six it started with. So a store can buy back what the night took, and a colony that gathers well can end the episode bigger than it started.
- Sprint: twice walking speed, costs energy, has a cooldown, and kicks up dust so you can see it. For getting to food before another colony does, and later for getting out of the way. Turning costs energy too, by how hard, so steering is cheap and spinning on the spot isn't.
- **Enough food to grow.** At first I wanted only enough food for about two colonies, so they'd race for it. With every colony running the same brain, though, which one makes it is down to place and luck, and in a world that lean half the Terrikins starved, turning in circles far from home. So 0.3 has enough food for colonies to grow if they forage well, eat when they need to and keep a store for the night. Scarcity comes back once each colony has its own brain (0.7).
- **Nectar flowers.** Now and then by day a flower opens somewhere, rich with nectar, and closes again after a few seconds. The first to reach it gets several foods' worth and a burst of speed for a while. It's rare and doesn't wait, so it's worth spotting from far off and sprinting to. Its colours are a rainbow lorikeet's.
- Foraging is checked in the colony world, not alone. Isolated ant workers die young even with food to hand (Koto et al. 2015), and a colony brain alone turned out the same way, so a lone Terrikin is scored as a number to watch, not held to what the 0.2 brain did.
- **Evals v2:** scripted foragers that carry food home (and one that also goes home at dusk) as the baselines, like greedy was for 0.2. Food stored and eaten, deaths and where they happen (away from the nest by day: a forager that couldn't feed itself), colonies through the night, how often another colony is close when food is eaten, how big colonies get, and seeds held back for the release. Head to head, too: a different brain in each colony of the same arenas, each taking every seat in turn.
- The brain is learned, never copied: forks that train side by side and copy whichever is doing best (population-based training) are how it gets there.

Done when creatures carry food home and store it, colonies get through all three nights on the store and by huddling, colonies grow by hatching new Terrikins from their store, and the brain beats the one it started from.

Two things I wanted here moved to 0.4: Terrikins not starving with jelly at home, and foragers away from the nest keeping themselves fed. Most of the 0.3 brain's deaths are still like that, and a brain that can't tell how long it's been out can't know when to head back, so I think they need memory first.

## 0.4 Elderflower: Growth and memory

*Our own machines first, rented GPUs when they're full.* A brain that remembers, Terrikins that eat from their store when they need to, and colonies that grow and shrink with what they gather, in worlds that don't have to start over. In 0.3 a Terrikin forgot food the moment it was out of sight and couldn't tell how long it had been out, so getting back to a patch, or home before it ran out, needed more than it had. A colony could only grow by two, and nothing paid it for growing.

**Memory** is a few numbers the brain carries from one choice to the next, its notes. It's the biggest change to the brain since 0.2, so it went in on its own first.

It comes in milestones. The numbers go in the order they ship, so the later ones may swap.

- **0.4.0 Memory that steers (done, 7 November 2026).** In a nursery with an apple tree out of sight of home, a Terrikin's own notes hold where the tree is and take it back there. Notes from a game whose tree lay the other way pull it that way, and when the tree moves while it's underground, it walks to the empty spot first. Three brains, on seeds never used for choosing them ([finding 0004](docs/findings/0004-the-notes-hold-the-trees-place.md); [notes](docs/notes/0.4.md), "A tree they go back to").
- **0.4.1 Home before dark, fed from the store.** In the tree world with nights and grown-up costs, a Terrikin gets home before the dark catches it out, and a hungry one eats there, even with nothing to carry. Most of the 0.3 brain's deaths were Terrikins starving with jelly at home, or out foraging without feeding themselves, and in the first night tests they died in the dark several metres out with jelly waiting at home ([finding 0012](docs/findings/0012-the-night-brain-comes-home-by-the-light.md), a hint).
  - Done when 85% or more are alive at the end of 256 games with two nights, on seeds never used for choosing, for three brains, and they bring home no less by day than the brains they started from.
  - Done when a hungry Terrikin with an empty crop inside a stocked nest eats within 2 s in 90% of starts.
  - Done when foragers away from the nest by day die at most half as often per minute out as today's brains, in the same world.
- **0.4.2 A world that keeps going.** A world that can be saved, picked up again later or on another machine, and left running with no end to the game, so growth can compound and the slow failures show: stores running down over days, patches grazed bare, boom and bust. The sim is arrays and physics bodies, so this didn't need to wait for 1.0.
  - Done when a world saved partway through and resumed plays on exactly as one that never stopped: the replays match, every random number included.
  - Done when a colony world with no end, run with scripted colonies for a few days of world time, holds a population the whole way in a rich setting, and in a lean one shrinks without dying out at once. This comes before any brain lives there: if scripted colonies can't last in a world, a brain won't either.
- **0.4.3 A patch remembered, in a colony.** In a colony world whose patches lie beyond sight and smell of home, a memory brain gets back to a patch it knows more often with its notes than without.
  - Done when a scripted forager that remembers patches beats a scripted carrier by a margin a brain could win, measured before any training.
  - Done when kept notes beat notes wiped at every unload on getting back to a known patch, the interval clear of zero, for three brains on fresh seeds, with colonies no smaller than the colony brain it started from.
- **0.4.4 Hatchlings that grow on food.** What hatches starts small and slow, feeds from the store while it's at the nest, and grows up on what it eats, not on a timer. Body traits (size, speed) become inputs, so one brain works for every size. The arena has room for so many Terrikins in all, and one colony growing leaves less room for the others, so a colony that brings home more ends bigger, and the food is the limit.
  - Done when a hatchling that's never fed never grows up, and one its colony feeds does.
  - Done when in a rich world a well-fed colony ends bigger than it started and in a lean one it shrinks, with scripted colonies first, then the brain, for three brains.

0.4 is finished when 0.4.1 to 0.4.4 all hold in one colony world with one recommended brain in `brains.toml`. It's announced on the site, not renumbered.

Once hatchlings grow, passing food mouth to mouth, as ants feed their larvae, gets tried, so nursing can become a job. **Mazes** are one of memory's test worlds rather than a track of their own: one Terrikin, a new maze every game, food only at the end, scored on mazes it has never seen by how close it gets to the shortest way, and how much faster it gets on a second and third run through the same one.

Moved out of 0.4: a brain for each colony, and colonies founding new ones, go to 0.7, where rivals give the world something to pick between. A bigger garden and seeing which nestmates come home loaded go to Later.

## 0.5 Foxglove: The way home

*Rented GPUs.* A world with more to remember, now there's a brain that can, and the first world people can drop in on.

- **Smelling the way home.** The exact sense of where the nest is goes, faded out over training. Each nest gives off its colony's scent instead, so close by they can smell home, and further out they have to remember the way.
- **Keeping the nest clean.** Droppings become real: they smell, and they're bad to live beside, either through a sickness that spreads to nestmates close by or through the room they take up, so carrying them away from the nest becomes a job, like an ant colony's waste heap.
- The first danger: a dust devil drifts across the arena, knocking creatures over (they lie still for a moment) and making them drop what they carry. It's weather, not a creature: nothing about it learns.
- **The live dome on the site.** A saved world from 0.4.2 left running, sent to the site as short replay chunks with a world clock, so anyone can drop in on a colony that's been going for days.

Done when foragers find their way home by smell, creatures keep clear of dust devils, and the dome on the site runs for a full day with at least one colony alive.

## 0.6 Gorse: Working together, moving things

*Rented GPUs.* Signal patch (free at first), scent marks (cost energy), rich food that needs two carriers, and blocks of varying weight, some needing two creatures.

- Two scent marks, one that draws others and a "no entry" one, as Pharaoh's ants use, laid on the same smell the food has. Both learned: no scripted trail-layers to get them started, even though that makes the first trails harder to find.
- Shivering: spending energy to warm nestmates close by, so huddling can split into heaters and passengers, as it does in honeybees.
- With dust devils about, a signal has more to mean than "help me carry this".
- A signal comes in only where the world already gives it something to mean (eating makes a sound, say), never as a free action in the hope it comes to mean something. The call I tried in 0.4 started out meaning nothing, and after 32M samples it still meant nothing: calling only pays once others come to calls, and coming only pays once calls mean something ([notes](docs/notes/0.4.md)).
- **Moving blocks on purpose.** Walking into a block isn't enough to move it: a hard push, costing energy, moves it the way the Terrikin is going. Blocks in the way of food first, then heavier ones that need two. In 0.3's tries, light blocks got pushed aside by Terrikins just walking at food, which isn't the same as moving them on purpose, and a grab-and-drag for doors never got learned (notes 0.3).
- Shove: knocks the target back and makes it drop what it's carrying, no damage. Costs energy, has a cooldown. For clearing paths and moving things, and the same knock and drop as the dust devil's.
- The store's hunger limit loosened, so a creature can eat jelly it doesn't need. Nestmates can shove it off: caught in the act, not by reputation. Learning to shove nestmates first means it's already a skill when rivals arrive.

Done when pairs team up on heavy food and heavy blocks, and creatures move things for a purpose. Maybe the first barriers, and freeloaders pushed off the store. Watch for signals or trails starting to mean something, warnings especially.

## 0.7 Honeysuckle: Rivals, conflict and lineages

*Rented GPUs.* Shoving rivals and stealing first, then attack, health and death. Friendly fire ramped in.

- Rivals can take jelly from a nest's store and carry it home; the colony can push or fight them off.
- Self-play against a pool of past brains, drawn from the lineage, so a colony can't get good at beating only the rival in front of it.
- **A brain for each colony.** Each colony's Terrikins learn from their own colony only, with its own reward blend and dials. Colonies that do well found new ones carrying copies of their brain, and colonies that die out take theirs with them, so the world picks which brains carry on, not a score I choose. What changes from parent to child is small, like the drives (what each one is paid for) and the body; what they do with them is still learned. It's here rather than in 0.4 because rivals give the world something to pick between, and with a brain each, food can be lean again so colonies race for it.
- Evals: how big each colony gets and how long it lasts, head to head between colonies' brains, and colonies founded.

Done when there's stealing, guarding of food patches, fights and retreats, and two lineages have grown apart, tested head to head in worlds neither trained in, with the seat a colony starts in either explained or no longer deciding who wins. Possibly warning signals before attacks.

## 0.8 Ivy: Queen and requeening

*Rented GPUs.* A queen who lays the eggs, brood that needs feeding and guarding, and a colony that can lose its queen and raise a new one with food and time. The queen is a body with her own place in the colony, not a script: what she does, and what the rest do about her, is learned. Raiding rival brood becomes possible.

Done when there are guards staying home, nurses near the brood, raids on rival nests, and colony crises and comebacks.

## 0.9 Juniper: Farming and seasons

*Rented GPUs.* Seeds, fertile soil, lean seasons.

Done when colonies plant and defend farms, and different colonies settle on different strategies. The big one.

## 1.0 Kingcup: The main world

*Rented GPUs or a small always-on server.* One continuous real-time world.

- **World state saved apart from the brains,** versioned, and moved forward to new versions instead of reset. It grows out of 0.4.2's saved worlds and 0.5's dome.
- Swapping in a new brain without wiping the world.
- The viewer streams the live world as well as playing replays.

Done when it's running, worth checking in on, and the dome has kept going for a month.

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
- A bigger garden with more Terrikins in it, once a world needs the room
- Seeing which nestmates come home loaded, the way harvester ants judge how much food is out there

## Tracks

Worked on beside the stages, with their own small milestones and no stage numbers.

- **Viewer and site:** the ghost tree (where a brain's notes put the tree, drawn faintly in the viewer), the night clips, and the live dome with 0.5. Their releases ride the stages' milestones.
- **Kids:** [Catch them!](docs/kids.md), with a carry button and a few cheap levels next. It gets its own release notes, not a version number.
- **Pets:** one Terrikin to look after, around the real forager brain, once worlds can be saved (0.4.2).
- **Compute:** Terrarium at Home (friends lending their machines) and keeping the machines we have busy. Built when a training line is waiting on it, not for its own sake.

Walking and Lab are parked, not before 0.6.

## Walking (parked)

A separate track, worked on beside the colony stages. In the sim a Terrikin slides on a plane, and its waddle is only the viewer's. The walker is an ant instead: a head, thorax and gaster, six legs of three parts each, a motor at every leg joint, feet that feel the ground, and a centre of mass it has to keep over its feet (`&ant` in the viewer shows the body, walking a hand-made gait for now). In 3D physics, a small body brain learns to stand, then to walk where it's asked, taking a colony brain's thrust and turn as what it's asked to do. Knocked over (from 0.5) becomes something it has to get up from. It's the step towards a real robot. It learns to walk from rewards and costs alone, never from recordings of how real animals move.

## Lab (parked)

A long-running track beside the stages: arenas copied from the classic bee and ant experiments, used to measure how close the Terrikins get to the real thing. Each one is set up from the original paper, and scored the same way the researchers scored the insects.

- **Bees:** counting, putting zero below one, telling same from different, visiting several flowers in a good order, finding the way home by the sun, and dances that say where food is.
- **Ants:** the double bridge (do they settle on the shorter way?), bridging a gap with their own bodies, choosing between two nest sites, and leading a nestmate to food.

Some of these the Terrikins may never do, and that's part of what it measures. The long-term goals behind it are real navigation, colonies with their own traditions that outlast the Terrikins who started them, and a colony that solves problems none of its members could alone, the way an ant colony works as one "liquid brain".
