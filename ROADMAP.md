# Roadmap

Each stage is a version: stage N opens as 0.N.0 with its first milestone, and each milestone after it ships as 0.N.y once it has been through the checks in [docs/releasing.md](docs/releasing.md). From 0.4.1 every milestone is a test in one main world that grows as they do, and 1.0 is that world left running for real. A stage's recommended brain has to beat the last stage's on the new stage's own world. Starting from the last stage's brain is still the first thing I try, but twice now a fresh brain has done better than one that started from an older brain, so where each brain came from is written down in `brains.toml` instead of being a rule.

What each mechanic is for is in [VISION.md](VISION.md). This is the order they arrive in, and what has to be true before a stage counts as done. From 0.4 on, every milestone's "done when" is small enough to check on its own, and it's met when a finding in [docs/findings](docs/findings/README.md) says so.

Each stage has a codename, a garden plant, going through the alphabet from Acorn at 0.0 to Kingcup at 1.0. The creatures are nims.

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

*Mac and rented GPUs.* Three colonies of six, a nest each, every nim with its own copy of the same brain. Find food, carry it home as jelly, get through the night on it, and grow the colony from what's stored.

- New inputs, added so the 0.2 brain still loads: whether a creature a ray hits is from the same colony. A flag rather than a colony number, so one brain works for every colony.
- Nests are something rays can see, own and other. Each creature also knows the distance and direction to its own nest, the way an ant keeps track of the way home. This may get fuzzier in later stages, so remembering and scent trails have something to do.
- The reward blend as a config dial.
- A crop, like an ant's social stomach: food eaten when already full is carried instead, slows the creature down, and is unloaded at the nest as jelly. Being full starts to mean something.
- **The jelly store.** One number per nest in the sim, drawn as a pile that grows. It feeds the colony, but eating jelly gives back less than the food was worth, and only a hungry creature can eat from it. Foraging should always pay better.
- Food grows in patches rather than evenly, since streams only form when food is clumped. Half of it grows in the middle, between the nests, so colonies meet over it.
- **Smell.** Food gives off a smell that spreads and fades, and only part of it gets past a block. A nim senses how strong it is and which way it gets stronger, so it can tell food is that way before it can see any: behind a block, round a wall, or past another nim.
- **Day and night.** Food stops growing at night and what's left standing goes, so the store is what gets a colony through to morning. Nights are cold: energy drains faster, less so in the nest or close to nestmates, so huddling can pay. They can sense the light, and dusk dims slowly, so night can be seen coming. Nights have to be longer than a nim can last on what's in its body, or there's no point keeping a store.
- **Hatching.** A store above a threshold pays jelly for an egg in the nest, which hatches a new nim, full-grown for now: in the place of one the colony lost, or in room for two more past the six it started with. So a store can buy back what the night took, and a colony that gathers well can end the episode bigger than it started.
- Sprint: twice walking speed, costs energy, has a cooldown, and kicks up dust so you can see it. For getting to food before another colony does, and later for getting out of the way. Turning costs energy too, by how hard, so steering is cheap and spinning on the spot isn't.
- **Enough food to grow.** At first I wanted only enough food for about two colonies, so they'd race for it. With every colony running the same brain, though, which one makes it is down to place and luck, and in a world that lean half the nims starved, turning in circles far from home. So 0.3 has enough food for colonies to grow if they forage well, eat when they need to and keep a store for the night. Scarcity comes back once each colony has its own brain (0.7).
- **Nectar flowers.** Now and then by day a flower opens somewhere, rich with nectar, and closes again after a few seconds. The first to reach it gets several foods' worth and a burst of speed for a while. It's rare and doesn't wait, so it's worth spotting from far off and sprinting to. Its colours are a rainbow lorikeet's.
- Foraging is checked in the colony world, not alone. Isolated ant workers die young even with food to hand (Koto et al. 2015), and a colony brain alone turned out the same way, so a lone nim is scored as a number to watch, not held to what the 0.2 brain did.
- **Evals v2:** scripted foragers that carry food home (and one that also goes home at dusk) as the baselines, like greedy was for 0.2. Food stored and eaten, deaths and where they happen (away from the nest by day: a forager that couldn't feed itself), colonies through the night, how often another colony is close when food is eaten, how big colonies get, and seeds held back for the release. Head to head, too: a different brain in each colony of the same arenas, each taking every seat in turn.
- The brain is learned, never copied: forks that train side by side and copy whichever is doing best (population-based training) are how it gets there.

Done when creatures carry food home and store it, colonies get through all three nights on the store and by huddling, colonies grow by hatching new nims from their store, and the brain beats the one it started from.

Two things I wanted here moved to 0.4: nims not starving with jelly at home, and foragers away from the nest keeping themselves fed. Most of the 0.3 brain's deaths are still like that, and a brain that can't tell how long it's been out can't know when to head back, so I think they need memory first.

## 0.4 Elderflower: One world with everything in it

*Our own machines first, rented GPUs when they're full.* A brain that remembers, nims that eat from their store when they need to, and colonies that grow and shrink with what they gather, all in one world that keeps going. In 0.3 a nim forgot food the moment it was out of sight and couldn't tell how long it had been out. A colony could only grow by two, and nothing paid it for growing.

**Memory** is a few numbers the brain carries from one choice to the next, its notes. It was the biggest change to the brain since 0.2, so it went in on its own first.

For two weeks after that, each skill got a small world of its own, a nursery: grazing standing still, drinking at a pond, jumping for apples, getting through the night. Each one worked in its nursery, and none of it reached a world that had all of it, so nothing added up. From 0.4.1 there's one main world instead: two colonies, with every skill that has worked on its own. Every milestone after that is a test in the main world, not a world of its own. A nursery is only for working out why something fails there, and whatever fixes it goes back into the main world the same day.

Before any brain trains for a milestone, a scripted nim that senses only what a nim senses has to be able to do it, so I know it can be learned from what they've got, and today's brain is scored there untrained, to see how far off it is. Every checkpoint on the main line also runs the skills battery: a frozen test for each skill a nursery taught (stands to graze, drinks standing still, jumps for apples, goes back to the tree it remembers, stays home at night), so a skill that fades while the world still pays for it shows up the same day. A brain still learning can dip; the brain I recommend at the end of a milestone has to keep every skill the world still needs. A brain twice as wide trains beside the working one, and it's reported whether it helps or not. If the working one forgets and the wider one doesn't, size is the limit; if both forget, I check the reward, what they got to practise, and the brain, before deciding which one is wrong. Two training runs in a row that don't help send it back to working out why, not on to a third. The night taught me that one: two weeks of runs trying to get them home, when the real trouble was that they couldn't see a tree 12 m away ([finding 0040](docs/findings/0040-the-night-block-is-the-far-tree.md)).

Each milestone also says what it puts on screen, since the reels are how people follow along.

- **0.4.0 Memory that steers (done, 7 November 2026).** In a nursery with an apple tree out of sight of home, a nim's own notes hold where the tree is and take it back there. Notes from a game whose tree lay the other way pull it that way, and when the tree moves while it's underground, it walks to the empty spot first. Three brains, on seeds never used for choosing them ([finding 0004](docs/findings/0004-the-notes-hold-the-trees-place.md); [notes](docs/notes/0.4.md), "A tree they go back to").
- **0.4.1 The main world.** Two colonies of nine in a 26 m arena: berries in patches, grass that feeds a nim more the slower it goes ([finding 0031](docs/findings/0031-grass-nims-stand-to-graze.md)), one pond that waters a nim more the slower it goes ([finding 0030](docs/findings/0030-pond-nims-stop-once-the-reward-stops-paying-for-turnover.md)), an apple tree in the middle to jump for, nights where resting and sleeping cost less than walking, sight to 12 m ([finding 0040](docs/findings/0040-the-night-block-is-the-far-tree.md)), and a fat reserve. Scripted nims that graze, drink and jump keep both colonies going in every game, though hatchlings stand in for a lot of the dead. Every brain I had going in dies out: none of them has learned to drink in a world that has everything else too (the night brains trained with water off), and the night brains never learned to settle at home. Water is the tight part: a full drink lasts 83 s and a night takes 60 s of it, so a nim has to drink late in the day to stay home all night. This takes the place of "Fed through the night". In the night nursery six brains averaged about 81% alive after two nights, two of them past 85%.

  The tools for the rest of 0.4 come in here too, so they're ready before the milestones that need them: a world that can be saved partway and played on, the score as a card (thrive: how many nims across a long game; adapt: change the world partway and see how fast they recover; skills: the battery), and a check that hatching doesn't eat the store the foragers need tomorrow (frozen brains, hatching on and off). Every count says whether it means the nims a game started with or the colony as it is, hatchlings included.
  - Done when, before any training, scripted colonies hold their numbers there and a scripted nim with only a nim's senses lives there.
  - Done when three trained brains live longer and bring home more food than the brains they started from, and both colonies are still there in at least 95% of 256 games of 360 s, on seeds never used for choosing. The finding gives the starting nims apart from hatchlings, how many are left in each colony, and every seed tried. This is the first main world that works, not the last word on survival.
  - Done when a world saved partway through and played on from its file matches one that never stopped, every random number included, and a save made on one machine plays on on another (the finding says which machines match exactly).
  - Done when the battery runs on every checkpoint, the recommended brain keeps its skills, and the wider brain beside it is reported either way.
  - On screen: the swoop into the dome, then one colony's day: grazing, the drink at the pond, a jump at the tree, everyone home at dusk.
- **0.4.2 Two speeds.** The brain decides every 0.2 s, and what's coming fades fast: something 20 s off counts for about a third, a minute off for about 5%. Stocking the nest for the second night pays off a minute or more after the choice, so it barely counts: in the night nursery, nests that went into the second dusk with two or fewer in the store lost most of their nims, and nests with five or more lost almost none. That's a strong lead, not a proof that the horizon is what stops them. Making the future fade slower did more harm than good both times I tried it ([finding 0014](docs/findings/0014-the-needs-reward-lifts-the-night-brains.md), [finding 0025](docs/findings/0025-pond-nims-plateau-and-time-in-the-pond-caps-them.md)). So the brain gets a slow part that picks a goal every couple of seconds and a fast part that steers toward it every 0.2 s, and I test whether that helps them look further ahead, against a one-speed brain given the same experience and the same reach into the future. The goals don't come with names: the brain gives them their meaning, and a version with named goals (graze, drink, home, tree, rest) trains beside it to see what the names are worth. A goal can be dropped the moment something happens, so the slow part never makes them slow to react. Animals are built the same way: a fly's escape skips the parts of its brain that find the way. This milestone opens with a look at the whole brain and body: how fast each part decides (reflexes, steering, goals), where memory sits, whether each sense gets its own region, and which senses ants and bees have that nims don't (counting steps, telling a nestmate by touch, an inner clock; nims already have a sky compass), and which milestone would need each one.
  - Done when 85% or more of the nims a game starts with are alive after the second dawn in the main world, in 256 games on seeds never used for choosing, for three brains. Every brain trained for it is reported, not just the ones that pass.
  - Done when more colonies go into the second dusk with enough food, water and energy for the mouths they have than with a one-speed brain trained on the same samples and looking as far ahead.
  - Done when it reacts to something sudden no slower than the one-speed brain (a new test in the battery), and keeps every skill.
  - On screen: a small mark over each nim for the goal it's on, and the colony switching to stocking up before dusk.
- **0.4.3 Mess and illness.** Droppings start to matter. A nim near them can fall ill, an ill nim burns more and can pass it on to nestmates beside it, so carrying droppings away from the nest becomes a job, like an ant colony's waste heap. Crowding as a second cause comes later. It means the world, not a cap, is what holds a colony's size down. Illness is a slow failure, so this is also where the world keeps going, with no end to the game, on the saves built in 0.4.1. From here on every milestone ends with a long look: the recommended brain lives in one world for two weeks to a month of world time, and each day's colony sizes, hatchings, deaths by cause and store go in a chart beside a replay of the best bits. Berry seeds also start passing in droppings and sprouting where they land. Nobody's meant to understand that yet: it's farming, there to be found.
  - Done when scripted colonies hold their numbers through ten days of world time with illness on, and a colony that never tidies does worse than one that does.
  - Done when three brains carry droppings out of the nest without being paid for it directly, fall ill less, and keep their colonies bigger than the 0.4.2 brain does in this same world with illness on, and every skill kept.
  - On screen: a week of one world in a minute, the waste heap growing outside the nest, a sick nim's colour fading.
- **0.4.4 Out of reach.** The tree's low apples run out by the afternoon, and what's left hangs above jump height. There's a block nearby. Push it under the tree, climb on, jump. Nims can't stand on anything yet (a jump today is only a height over a flat world), so that gets built first: a block's height, standing on top, landing on it, stepping or falling off, and jumping from there. It's taught alongside in a small world of its own: a light goes green and a treat drops in a zone; then pushing a block into the zone is what turns the light green; later a person can press the button while they watch. If running out doesn't bring it out, high apples as an extra on top get a try.
  - Done when a scripted nim gets the high apples with the block.
  - Done when, in the green-light world, three brains push the block into the zone in 70% or more of games, where an untrained brain almost never does.
  - Done when, in the main world, three brains get a high apple in 50% or more of the chances they have, at least 20 points more than in the same world with a block that gives no height, and every skill kept.
  - On screen: a nim shoving a block under the tree, climbing up and jumping.
- **0.4.5 The other colony.** A nim can take jelly out of the other colony's store and carry it home. The defence is a charge: a sprint into a rival that drains its stamina and makes it drop what it's holding, and costs the one charging some stamina too. Nobody gets hurt yet. Nims can already tell a nestmate from a rival by sight; telling one by touch or smell when it's out of sight comes out of 0.4.2's look at the senses. Raiders are scripted first, then both colonies run the brain. The flowers already in the world start refilling stamina, and alarm calls get tried beside it.
  - Done when, before training, colonies that guard keep more of their store against scripted raiders than colonies that don't.
  - Done when three brains keep more of their store against scripted raiders than the 0.4.4 brain does with the same raids on, and raid when they get the chance.
  - Done when, in games of a set length with raiding on, both colonies are still there as often as with the 0.4.4 brain, colonies are no smaller, and every skill is kept.
  - On screen: a raider slipping out with a jelly, charged down, the jelly dropped in the grass.
- **0.4.6 Trails.** A nim carrying food home leaves a scent where it walks, and it fades. Nobody decides to lay it: for now it's how the world works, like droppings. What gets learned is following it back out to where the food was, so one nim's find becomes the colony's. Choosing when to lay a trail, and a "no entry" one, stay in 0.6. Following a smell is learnable already: trained on the scent of a tree, the night brains kept 12 to 28 more nims in a hundred alive than the brains they started from.
  - Done when, in the main world, trails cut the time spent searching by a quarter or more, against the same brain with the trail removed and with it scrambled, with no fewer nims alive, for three brains.
  - On screen: ant roads forming between the nest and the bushes.
- **0.4.7 A bigger world, and places remembered.** The arena grows to about 50 m and the day gets longer (four or five minutes), so far trips fit. Bushes run down as they're picked, some die and come back somewhere else, and patches and the pond lie beyond sight and smell of home, so getting back to one a nim has found takes memory. The sense of where home is gets less exact the further a nim walks, as it does for ants (put them on stilts and they overshoot), and comes good again at the nest. Hiding food and coming back for it gets a try. The energy has to be set as a budget first: a 10.7 s trip to the tree costs 0.32 and brings home 0.8, only about two and a half times its cost, a thin margin for a learner, and halving walking's cost filled the colonies with no training at all. So the world check says how long a full nim lasts resting and walking and what a trip costs against what it brings back, aiming at trips that bring home about five times their cost. One thing changes at a time here, each measured before the next.
  - Done when the same scripted forager, once remembering where patches are and once not, shows remembering is worth having, before any training.
  - Done when kept notes beat notes wiped at every unload on getting back to a known patch, and at every drink on getting back to the pond, the interval clear of zero, for three brains on fresh seeds, with colonies no smaller than the brain they started from.
  - Done when, after a bush dies, colonies find food again faster than the 0.4.6 brain's do.
  - On screen: two nims side by side, one with its notes, one with them wiped.
- **0.4.8 Hatchlings that grow on food, and grow old.** What hatches starts small and slow, feeds from the store while it's at the nest, and grows up on what it eats, not on a timer. Body traits (size, speed) become inputs, so one brain works for every size. The arena has room for so many nims in all, so a colony that brings home more ends bigger, and the food is the limit. Nims also get old and die after a lifespan (a few days of world time to start), so a colony only lasts by hatching. Today an egg hatches when the store reaches a set amount, which can drain the store the foragers need tomorrow (0.4.1 checks how much), and laying as something the colony chooses gets tried here. Feeding hatchlings mouth to mouth, as ants feed their larvae, gets tried too, so nursing can become a job.
  - Done when a hatchling that's never fed never grows up, and one its colony feeds does.
  - Done when in a rich world a well-fed colony ends bigger than it started and in a lean one it shrinks, with scripted colonies first, then the brain, for three brains.
  - Done when, in a world that keeps going, a colony that never hatches dies out of old age, and one that hatches is still there after three lifespans.
  - On screen: a hatchling growing up.

0.4 is finished when 0.4.1 to 0.4.8 all hold in the main world with one recommended brain in `brains.toml`. It's announced on the site, not renumbered.

Before nursing, I want to know whether colonies already split the work: each nim's share of what comes home, its time at home, and how old it is when it first goes out. Clonal ants in groups of six split into jobs with no differences between them to start from, so it's worth checking whether the same nim keeps the same job. **Mazes** are one of memory's test worlds rather than a track of their own: one nim, a new maze every game, food only at the end, scored on mazes it has never seen by how close it gets to the shortest way, and how much faster it gets on a second and third run through the same one.

Moved out of 0.4: a brain for each colony, colonies founding new ones (a colony that grows big enough splitting in two) and harm between colonies go to 0.7. Seeing which nestmates come home loaded goes to Later. Water and keeping the nest clean came in from 0.5.

## 0.5 Foxglove: The way home

*Rented GPUs.* A world with more to remember, now there's a brain that can, and the first world people can drop in on.

- **Smelling the way home.** The exact sense of where the nest is goes, faded out over training. Each nest gives off its colony's scent instead, so close by they can smell home, and further out they have to remember the way.
- The first danger: a dust devil drifts across the arena, knocking creatures over (they lie still for a moment) and making them drop what they carry. It's weather, not a creature: nothing about it learns.
- **The live dome on the site.** A saved world from 0.4.3 left running, sent to the site as short replay chunks with a world clock, so anyone can drop in on a colony that's been going for days.

Done when foragers find their way home by smell, creatures keep clear of dust devils, and the dome on the site runs for a full day with at least one colony alive.

## 0.6 Gorse: Working together, moving things

*Rented GPUs.* Signal patch (free at first), scent marks (cost energy), rich food that needs two carriers, and blocks of varying weight, some needing two creatures.

- Trails laid by choice. From 0.4.6 a nim carrying food leaves a scent without deciding to; here laying one becomes something it does, and costs energy, with two marks, one that draws others and a "no entry" one, as Pharaoh's ants use. Both learned: no scripted trail-layers to get them started.
- Shivering: spending energy to warm nestmates close by, so huddling can split into heaters and passengers, as it does in honeybees.
- Carrying costs energy by its weight as well as slowing a nim down, so a load and a body's heat are both paid for, beside pushing blocks and shivering.
- With dust devils about, a signal has more to mean than "help me carry this".
- A signal comes in only where the world already gives it something to mean (eating makes a sound, say), never as a free action in the hope it comes to mean something. The call I tried in 0.4 started out meaning nothing, and after 32M samples it still meant nothing: calling only pays once others come to calls, and coming only pays once calls mean something ([notes](docs/notes/0.4.md)).
- **Moving blocks on purpose.** Walking into a block isn't enough to move it: a hard push, costing energy, moves it the way the nim is going. Blocks in the way of food first, then heavier ones that need two. In 0.3's tries, light blocks got pushed aside by nims just walking at food, which isn't the same as moving them on purpose, and a grab-and-drag for doors never got learned (notes 0.3).
- Shove: knocks the target back and makes it drop what it's carrying, no damage. Costs energy, has a cooldown. For clearing paths and moving things, the same knock and drop as the dust devil's and as 0.4.5's charge at raiders.
- The store's hunger limit loosened, so a creature can eat jelly it doesn't need. Nestmates can shove it off: caught in the act, not by reputation. Learning to shove nestmates first means it's already a skill when rivals arrive.

Done when pairs team up on heavy food and heavy blocks, and creatures move things for a purpose. Maybe the first barriers, and freeloaders pushed off the store. Watch for signals or trails starting to mean something, warnings especially.

## 0.7 Honeysuckle: Rivals, conflict and lineages

*Rented GPUs.* Stealing and the charge came in 0.4.5. Here come attack, health and death, with friendly fire ramped in, as the last of the things that keep a population in check after food and illness.

- Raiders that took jelly in 0.4.5 can now be fought off, and fights can hurt.
- Self-play against a pool of past brains, drawn from the lineage, so a colony can't get good at beating only the rival in front of it.
- **A brain for each colony.** Each colony's nims learn from their own colony only, with its own reward blend and dials. Colonies that do well found new ones carrying copies of their brain, and colonies that die out take theirs with them, so the world picks which brains carry on, not a score I choose. What changes from parent to child is small, like the drives (what each one is paid for) and the body; what they do with them is still learned. It's here rather than in 0.4 because rivals give the world something to pick between, and with a brain each, food can be lean again so colonies race for it.
- Evals: how big each colony gets and how long it lasts, head to head between colonies' brains, and colonies founded.

Done when there's stealing, guarding of food patches, fights and retreats, and two lineages have grown apart, tested head to head in worlds neither trained in, with the seat a colony starts in either explained or no longer deciding who wins. Possibly warning signals before attacks.

## 0.8 Ivy: Queen and requeening

*Rented GPUs.* A queen who lays the eggs, brood that needs feeding and guarding, and a colony that can lose its queen and raise a new one with food and time. The queen is a body with her own place in the colony, not a script: what she does, and what the rest do about her, is learned. Raiding rival brood becomes possible.

Bodies of very different sizes (queen, brood, workers) mean what living and moving cost scales with a body's mass, in place of a separate share for each kind. A replete caste gets tried here too: honeypot ants keep the colony's store in the swollen crops of nestmates who stay home, which is how a big body reserve can sit beside a store instead of making it pointless.

Done when there are guards staying home, nurses near the brood, raids on rival nests, and colony crises and comebacks.

## 0.9 Juniper: Farming and seasons

*Rented GPUs.* Seeds, fertile soil, lean seasons.

Lean seasons are the first lean times longer than a brain looks ahead, and they're what fat is really for. A small reserve is already in the main world from 0.4.1 (food eaten past full slowly turns into fat, at a loss, and burns back when food runs short, enough for a night). Here it grows to carry a nim through lean days, while staying smaller than a lean season, or the colony's store loses its point.

Walls and windbreaks from pushed blocks get tried for the cold, and storms come with the seasons.

Done when colonies plant and defend farms, and different colonies settle on different strategies. The big one.

## 1.0 Kingcup: The main world, left running

*Rented GPUs or a small always-on server.* One continuous real-time world.

- **World state saved apart from the brains,** versioned, and moved forward to new versions instead of reset. It grows out of 0.4.3's saved worlds and 0.5's dome.
- Swapping in a new brain without wiping the world.
- The viewer streams the live world as well as playing replays.
- One energy ledger the whole world balances to, since nothing starts over.

Done when it's running, worth checking in on, and the dome has kept going for a month.

## Later

- More to night: shorter sight in the dark, glowing signals easier to spot, night raids
- Castes (different body traits at spawn; the colony chooses what to spawn)
- A small energy cost for colour signalling (more honest signals)
- Disguise and impersonation as a deliberate unlock
- The queen as a thinking agent
- Genetics, inheritance, pairing
- Bee-style dances
- Learning from each other within a life: a trick one nim finds spreading through its colony, as string pulling spread through bumblebees. Needs memory first, and probably more than reward alone.
- True height: ramps and ledges
- Dealing with nestmates that don't pull their weight over time, not just when caught in the act. Needs telling individuals apart, and longer memory.
- Seeing which nestmates come home loaded, the way harvester ants judge how much food is out there

## Tracks

Worked on beside the stages, with their own small milestones and no stage numbers.

- **Viewer and site:** the ghost tree (where a brain's notes put the tree, drawn faintly in the viewer), the night clips, and the live dome with 0.5. Their releases ride the stages' milestones.
- **Kids:** [Catch them!](docs/kids.md), with a carry button and a few cheap levels next. It gets its own release notes, not a version number.
- **Pets:** one nim to look after, around the real forager brain, once worlds can be saved (0.4.3).
- **Compute:** Terrarium at Home (friends lending their machines) and keeping the machines we have busy. Built when a training line is waiting on it, not for its own sake.

Walking and Lab are parked, not before 0.6.

## Walking (parked)

A separate track, worked on beside the colony stages. In the sim a nim slides on a plane, and its waddle is only the viewer's. The walker is an ant instead: a head, thorax and gaster, six legs of three parts each, a motor at every leg joint, feet that feel the ground, and a centre of mass it has to keep over its feet (`&ant` in the viewer shows the body, walking a hand-made gait for now). In 3D physics, a small body brain learns to stand, then to walk where it's asked, taking a colony brain's thrust and turn as what it's asked to do. Knocked over (from 0.5) becomes something it has to get up from. It's the step towards a real robot. It learns to walk from rewards and costs alone, never from recordings of how real animals move.

## Lab (parked)

A long-running track beside the stages: arenas copied from the classic bee and ant experiments, used to measure how close the nims get to the real thing. Each one is set up from the original paper, and scored the same way the researchers scored the insects.

- **Bees:** counting, putting zero below one, telling same from different, visiting several flowers in a good order, finding the way home by the sun, and dances that say where food is.
- **Ants:** the double bridge (do they settle on the shorter way?), bridging a gap with their own bodies, choosing between two nest sites, and leading a nestmate to food.

Some of these the nims may never do, and that's part of what it measures. The long-term goals behind it are real navigation, colonies with their own traditions that outlast the nims who started them, and a colony that solves problems none of its members could alone, the way an ant colony works as one "liquid brain".
