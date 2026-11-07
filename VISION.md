# Vision

A small, persistent 3D world of cute blob creatures, trained with reinforcement learning, that form colonies, forage, farm, guard, signal with colour, raid each other, and raise a queen. Inspired by OpenAI's hide-and-seek emergent tool use, ant scent trails and farming, and honeybee colony life.

This document is the shared picture. It describes **what** the world is and **why** each mechanic exists. Implementation details are decided stage by stage.

---

## 1. Guiding principles

1. **Make things possible, never script them.** Farming, guarding, cooperation, deception and rogues are not taught. The world makes them possible and worth it, and we watch for them. Possible isn't enough on its own, though: an action added and left to be found mostly isn't. Before a new mechanic or world, three questions. How well does a scripted creature do there, so there's room to learn? What shortcuts could a body take instead (a tree "out of sight" that wasn't, unloading at the rim so the body points back at the food)? And what pays at each step on the way? If a step pays for nothing, the world isn't ready.
2. **Every stage builds on the last.** New features are added so earlier training stays useful, and starting from the last brain is the first thing to try. It isn't a rule: a fresh brain has beaten an inherited one more than once, so a fresh start is fine when it's measured and written down.
3. **Small visible wins.** Every stage ends with something you can watch and, ideally, a clip worth sharing.
4. **Simulation and looks are separate.** The brain lives in a cheap, flat, simple world. The renderer makes it cute and 3D. Changing the look never requires retraining.
5. **Every balance number is a dial.** Costs, damage, reward blends and regrowth rates live in config, so tuning happens between stages without redesign.
6. **A world that keeps going.** The point is creatures worth caring about, and that needs a world that's still there tomorrow: saved, picked up again later or on another machine, never wiped for an update. The sim is arrays and physics bodies, so this comes early (0.4), not at the end.

---

## 2. The world at a glance

### Worlds
- **Training arenas** — many small, isolated, parallel episodes with randomised layouts. Run fast and headless. Replays recorded for viewing and sharing.
- **Dev world** — a sandbox copy of the main world for testing new brains and mechanics.
- **Main world** — one ongoing, real-time world with a fixed map. Versioned and checkpointed. Updates (bug fixes, new brains) are applied without wiping its state. Starts running once trained brains are good enough to make a continuous world interesting.

### Simulation vs rendering
- **Simulation: 2.5D.** Creatures and objects move on a flat ground plane with simple physics: sliding, colliding, pushing. Nothing walks, falls or climbs. True height (ramps, ledges) can be added later if a stage needs it.
- **Rendering: full 3D.** Orbitable camera, lighting, shadows, decorative terrain. Creatures are small humanoid-ish blobs with procedural animation on top of the sim: squash and stretch, hops, wobble, eyes that look where they face, a glowing signal patch, and a glow that dims with low energy.

### Scale (main world)
- 3–4 colonies of 6–12 creatures each (roughly 20–50 creatures).
- Every creature runs its own copy of its colony's brain, acting on what it senses. Until 0.7 every colony carries copies of the same one. Each creature knows its own colony and body traits as inputs.

---

## 3. Creatures

### Body
- Simple capsule/blob in the sim.
- **Body traits as numbers from day one:** size, speed, push strength, carry capacity, max health. All identical at first. Castes later just means changing these at spawn.
- **Fixed body tint** in the colony's colour. Always truthful; this is how friend and foe are told apart.
- **Signal patch** — a part of the body that can change colour.

### Senses
- **Vision:** a fan of rays (lidar-style) returning distance and *what* was hit, including its colour category: food type, creature, colony tint, signal colour, queen, brood, block, wall, scent mark. Much cheaper than pixel vision and ideal for colour-based behaviour.
- **Self-state:** energy, health, what it's carrying, colony ID, body traits.
- A sense of distance and direction to its own nest, as ants keep track of the way home. It may get fuzzier later, so memory and scent trails have something to do.
- **A compass:** which way it's facing in the world. It's what lets memory hold a place: the notes keep where the tree is in the world's frame, not relative to the body, and taken away the notes hold the place about three times more loosely ([finding 0013](docs/findings/0013-without-a-compass-the-notes-hold-the-place-loosely.md), a hint).
- **Memory:** a few numbers the brain carries from one choice to the next, its notes. They hold where a hidden tree is and steer it back there ([finding 0004](docs/findings/0004-the-notes-hold-the-trees-place.md)).

### Actions
- Move (direction + speed) and turn.
- **Sprint** — faster, costs energy, has a cooldown.
- **Pick up / drop** food, seeds, brood.
- **Shove** — no damage. Knocks back and makes the target drop what it's carrying. For stealing, warning, clearing paths.
- **Attack** — a separate, deliberate action that deals damage. Costs energy, has a cooldown, leaves the attacker open to counterattack.
- **Push/drag movable objects.**
- **Set signal patch** to one colour from a small shared palette (4–6 colours). The palette never includes colony colours, so no impersonation by default.
- **Drop scent mark** — a coloured ground marker that slowly fades. Costs energy. Readable (and fakeable) by anyone.
- **Plant seed.**

### Energy — the single currency
Food becomes energy. Sprinting, attacking, carrying heavy things, scent marks, and later signalling and egg-laying all spend it. Health recovers slowly through eating or resting at the nest.

### Damage and death
- Real damage, real death.
- **Friendly fire is on**, but ramped in gradually across training (damage scaled from 0 up to full) so it never wipes out earlier learning.

### Motivation (rewards)
A blend of **self** (energy, health, survival) and **colony** (food stored, population, brood, queen alive). Early stages lean on self-interest. Later stages shift weight toward the colony. Some self-interest always remains, so:
- a lone creature still survives as best it can when isolated, and
- freeloaders and rogue agents remain possible.

---

## 4. Colonies, brood and the queen

- Each colony has a **nest** and a **queen**.
- The queen is a body with her own place in the colony, not a script: she lays the eggs, and what she does, and what the rest do about her, is learned.
- **Brood:** eggs → larvae/pupae → hatchlings. Brood must be fed and protected. Rivals can attack or steal it.
- **Hatchlings** start small and weak, which naturally keeps them near the nest tending brood before they grow into foragers. This gives honeybee-style age-based roles without castes.
- **Losing the queen** is a crisis, not instant death. A queenless colony can raise a new queen by pouring jelly into one member over time, while defending the nest until she matures.
- The colony grows by succeeding and shrinks by starving, being raided, or losing fights.

---

## 5. Food and resources

| Resource | Behaviour | Strategy it rewards |
|---|---|---|
| Common food | Scattered everywhere, low value, regrows slowly | Basic foraging, solo survival |
| Rich food | Heavy, high value, in contested patches; needs two creatures to carry | Cooperation, signalling "help me", fighting over hotspots |
| Seeds | Can be carried and planted; grow slowly; thrive only on fertile soil | Farming, staying put, guarding territory |

**Jelly** is what food becomes once it's carried home, and the colony's one currency. Stored in the nest, it hatches new members and feeds the young; later it feeds the queen and raises a new one. Eating it back gives less than the food was worth, so foraging always pays better than living off the store.

**Movable blocks** of varying weight, some needing two creatures to move. Used for barriers, walling off farms and nests, and blocking chokepoints.

---

## 6. The map

- **Bounded map** with nests near the edges and a richer, contested middle.
- **Rocks and walls** create corridors and chokepoints to defend, ambush or block.
- **Fertile soil** patches spread unevenly, so some nests have good farmland and others don't. This asymmetry pushes colonies toward different strategies (farm-and-defend vs raid).
- **Lean seasons:** wild food periodically stops regrowing. This is the main pressure that makes farming and food storage pay off.
- **Day/night:** from 0.3, nights with no food and a cold that huddling and the nest keep off, so the store has a job. Later, shorter vision at night, glowing signals easier to spot, night raids possible.
- **Dust devils** wander across the map, knocking creatures over and scattering what they carry. Weather, not a creature.
- **Training maps are randomised** every episode so creatures learn general skills. The main world uses one fixed layout.

---

## 7. Technical direction (to be confirmed per stage)

Starting suggestions, to be checked stage by stage, not decisions.

- **Language/ML:** Python + PyTorch.
- **Physics:** the 2.5D design probably doesn't need PyBullet. A lightweight 2D physics engine or a custom vectorised sim may train far faster. Evaluate early, because simulation speed is the biggest factor in training cost. (Measured in 0.1: pymunk, see [docs/physics.md](docs/physics.md).)
- **Viewer:** a 3D renderer (e.g. a browser-based Three.js viewer) that plays back recorded episodes and, later, streams the live main world. Kept fully separate from the sim.
- **Algorithm:** PPO-style multi-agent training with every agent in a colony running a copy of its colony's policy (parameter sharing). Self-play against past checkpoints once colonies compete, so brains don't overfit to one opponent.
- **Brain architecture built to grow:** an entity-based design (attention over "things I can see", each with a type) handles new object types, food kinds and creature types by adding new types rather than reshaping the network. This is the main way earlier training survives new features.
- **Checkpoint discipline:** a stage starts from the previous stage's best checkpoint by default, its old skills are checked on the old stage's world, and a fresh start is allowed when it's measured and written down in `brains.toml`. Each rung also tries a fresh brain on a world two or three rungs on, beside the fork, to see what can be skipped. New inputs/actions start disabled or zero-weighted, then switch on. Every curriculum dial (reward blend, friendly-fire scale, signal cost) lives in config.
- **Compute:** early stages on the MacBook Air M3 (16GB). Move to RunPod GPUs when stages involve multiple colonies, self-play or long horizons.
- **Persistence:** a world's state (creatures, brood, food, objects, every random stream) is saved separately from brain weights, so a world can be resumed exactly and brains swapped without resetting it. Saving and resuming comes in 0.4; the main world builds on it.

---

## 8. Roadmap

The stages, what each one shows, and what has to be true before it counts as done are in [ROADMAP.md](ROADMAP.md). How versions, branches, brains and replays are kept is in [docs/releasing.md](docs/releasing.md).

---

## 9. Things to watch for (the "oh cool" list)

- A colony settling on farming while another settles on raiding.
- Guarding of food patches or farms, especially with walls built from blocks.
- Signal colours that consistently mean something ("food", "help", "danger").
- Scent trails leading to food.
- Deception: false signals or fake trails.
- Rival creatures sharing information when out exploring.
- Rogue or freeloading creatures, and how colonies respond.
- Age-based roles: young near brood, older out foraging.
- A queenless colony successfully raising a new queen.
