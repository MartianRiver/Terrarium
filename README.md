# Terrarium

My pet project, quite literally: a colony of little AI creatures living in a garden under a glass dome on Mars. They're called Terrikins.

Nothing they do is scripted. Each one sees the world through 16 rays, a small neural net turns what it sees into moves, and it learns by trial and error (reinforcement learning) from what it's rewarded for. The plan is to build the world up a stage at a time: one Terrikin learning to eat, then a colony that carries food home, then colour signals, scent trails, heavy food that takes teamwork, rivals, a queen and seasons, and in the end one world that keeps running. The long-term dream is a real little robot.

You can watch the latest one at [terrarium.martianriver.com](https://terrarium.martianriver.com).

## Where it's at

**0.2, Clover: one Terrikin teaching itself to eat (done).** It's alone in the arena with 8 berries and 3-minute lives, and if its energy runs out it starves. It's only rewarded for staying fed. After 52 minutes of training on my MacBook Air (20 million samples, about 11.6 days of practice in the world's own time), it eats 18.4 berries a minute and lives out every episode in the evals. Moving at random gets 0.26 and starves in under a minute. A scripted forager that heads straight for the nearest berry it can see gets 13.8, so the brain beats that too.

**0.3, Daisy: a colony (in progress).** Up to 12 Terrikins, one nest, each with its own copy of the same brain. The idea is that they carry food home in a crop, like ants do, store it at the nest as jelly, and the colony grows from its store. So far the brain can see the way home and tell its nestmates from strangers, and the 0.2 brain still loads and acts the same.

Each stage is a version, and each has a "done when" in [ROADMAP.md](ROADMAP.md). What each mechanic is for, and why, is in [VISION.md](VISION.md). Each stage gets its own reel on Instagram (#RiversTerrarium).

## How it works

- **The sim** (`sim/`, Python) is a flat 2D world: creatures, food, pushable blocks, walls and nests, with sliding and collisions from [pymunk](https://www.pymunk.org). Many small arenas run side by side for training. Every balance number is in a config file.
- **The brain** is a small transformer, about 70k parameters, that pays attention to its own state and to one token per ray. What it sees and does is an append-only list, so a new stage adds inputs instead of starting over, and every stage's brain begins from the last one. Trained with PPO.
- **The viewer** (`viewer/`, three.js) draws the same world in 3D from replay files: the garden, the dome, the Terrikins' waddle and faces. None of the looks affect the sim, so changing them never means retraining.

Every training run keeps a record of the code, config, parent brain and machine it came from, and only brains from committed code can become a stage's brain. What it all cost is tracked too: the 0.2 brain had about an hour of training behind it, on my Mac, for $0.

## How it's made

I build this with Claude Code, running Claude Opus (Opus 5.5 as I write this). I set where it's going: the stages and what each one is for, what has to be true before one counts as done, the rules (nothing scripted in a brain that gets carried forward; behaviour comes from rewards and costs, not hard-coded rules), and which way to go when something stalls. Claude writes most of the code and the scripts, runs the training and the evals, on my Mac and on GPUs I rent by the hour, and reports back. I read the results, push back, and decide. Some of the turns that mattered were mine, like giving them blocks they can grab and pull out of the way; some were Claude's, like finding that a new action was firing on half of all training ticks, which is why no crop ever made it home. Adversarial reviews of the code and the numbers catch what the day-to-day misses.

I've wanted a digital ant farm for a long time: something I could host online for people to watch over time. My first go, about two years ago, started from the very bottom, with walking, and I never got the animations working. The next try was an agar.io clone, to skip the walking problem altogether, but I had to redesign the game so much to make anything interesting happen that it never suited this, and it needed a lot of compute before it showed anything that made more compute and time feel worth spending. So this time I skipped real walking and went straight for the creature, something between a bee and an ant. Ants and bees, with their scent trails, their dances and their hive minds, are incredible animals, and I think we're finally at the point where we can grow some odd alien hybrid of them digitally, and faithfully: nothing scripted, no cheating the mind into looking clever.

A pet project like this only fits in the time I have because of agentic coding. The grunt work, all the scripting, and setting up and minding rented GPUs would otherwise take more hours than I've got.

The write-ups on [the site](https://terrarium.martianriver.com) are drafted by Claude from the run records and edited by me, and each one says so and names the model that drafted it. Every number in them comes from a run record, and I read every post and clip before it goes up.

## Running it

You'll need [uv](https://docs.astral.sh/uv/) and Node 24. I've only run it on macOS; CI runs it on Linux.

The viewer, with the scripted demo:

```
cd viewer
npm install
npm run dev
```

Open the address it prints. "Open replay" plays a replay file, like the ones in `samples/`.

The sim and the 0.2 brain:

```
cd sim
uv sync                  # on Linux: uv sync --extra cpu (or --extra cuda), and the same extra on every uv run
curl -LO https://github.com/MartianRiver/Terrarium/releases/download/v0.2.0/17cc35ad7932.pt
uv run python -m terrarium.evals --config configs/solo.toml --policy random greedy --brain 17cc35ad7932.pt
uv run python -m terrarium.record clover.jsonl.gz --config configs/solo.toml --seconds 180 --brain 17cc35ad7932.pt
```

Then open `clover.jsonl.gz` in the viewer.

Training your own:

```
uv run python -m terrarium.train my-first --world configs/solo.toml --scratch
```

With `uv run python -m terrarium.serve` running in `sim/`, the viewer's `/runs.html` shows every run's curves while it trains, and you can watch any checkpoint.

## More

- [docs/training.md](docs/training.md): how training works, what a run records, and how fast it goes on a Mac and on a rented GPU
- [docs/brain.md](docs/brain.md): what the brain sees and does, and how that grows between stages
- [docs/evals.md](docs/evals.md): how brains are scored
- [docs/replays.md](docs/replays.md): the replay format
- [docs/physics.md](docs/physics.md) and [docs/benchmark.md](docs/benchmark.md): why pymunk, and how fast the sim runs
- [docs/releasing.md](docs/releasing.md): versions, branches and what has to keep loading from one version to the next
- [CHANGELOG.md](CHANGELOG.md)

## Issues

Bug reports and ideas are welcome as issues; I'm not taking pull requests ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Licence

MIT ([LICENSE](LICENSE)).
