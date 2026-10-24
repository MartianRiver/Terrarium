# Terrarium

My pet project, quite literally: a colony of little AI creatures living in a garden under a glass dome on Mars. They're called Terrikins.

Nothing they do is scripted. Each one sees the world through 16 rays, a small neural net turns what it sees into moves, and it learns by trial and error (reinforcement learning) from what it's rewarded for. The plan is to build the world up a stage at a time: one Terrikin learning to eat, then a colony that carries food home, then colour signals, scent trails, heavy food that takes teamwork, rivals, a queen and seasons, and in the end one world that keeps running. The long-term dream is a real little robot.

You can watch the latest one at [terrarium.martianriver.com](https://terrarium.martianriver.com).

## Where it's at

**0.2, Clover: one Terrikin teaching itself to eat (done).** It's alone in the arena with 8 berries and 3-minute lives, and if its energy runs out it starves. It's only rewarded for staying fed. After 52 minutes of training on my MacBook Air (20 million samples, about 11.6 days of practice in the world's own time), it eats 18.4 berries a minute and lives out every episode in the evals. Moving at random gets 0.26 and starves in under a minute. A scripted forager that heads straight for the nearest berry it can see gets 13.8, so the brain beats that too.

**0.3, Daisy: a colony (in progress).** Up to 12 Terrikins, one nest, one shared brain. The idea is that they carry food home in a crop, like ants do, store it at the nest as jelly, and the colony grows from its store. So far the brain can see the way home and tell its nestmates from strangers, and the 0.2 brain still loads and acts the same.

Each stage is a version, and each has a "done when" in [ROADMAP.md](ROADMAP.md). What each mechanic is for, and why, is in [VISION.md](VISION.md). Each stage gets its own reel on Instagram (#RiversTerrarium).

## How it works

- **The sim** (`sim/`, Python) is a flat 2D world: creatures, food, pushable blocks, walls and nests, with sliding and collisions from [pymunk](https://www.pymunk.org). Many small arenas run side by side for training. Every balance number is in a config file.
- **The brain** is a small transformer, about 70k parameters, that pays attention to its own state and to one token per ray. What it sees and does is an append-only list, so a new stage adds inputs instead of starting over, and every stage's brain begins from the last one. Trained with PPO.
- **The viewer** (`viewer/`, three.js) draws the same world in 3D from replay files: the garden, the dome, the Terrikins' waddle and faces. None of the looks affect the sim, so changing them never means retraining.

Every training run keeps a record of the code, config, parent brain and machine it came from, and only brains from committed code can become a stage's brain. What it all cost is tracked too: the 0.2 brain had about an hour of training behind it, on my Mac, for $0.

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
