# Versions and releases

## Version numbers

`0.N.y` until the main world runs, then 1.0.

- **0.N.0** is stage N finished. The list for each stage is in [ROADMAP.md](../ROADMAP.md).
- **0.N.y** is a fix to a finished stage: no new mechanics, no new inputs or actions, no retraining.

Each release is a tag (`v0.2.0`) with an entry in [CHANGELOG.md](../CHANGELOG.md).

## Branches

- `main` is the last finished stage and nothing else. It only moves when a stage is released.
- `next` is the stage in progress. Each piece of work is a branch off `next`, squash-merged back by a pull request once its checks pass: the commit hooks, a read of the whole diff, and from 0.1 the CI checks and a benchmark no slower than the baseline (or the slowdown explained in the PR).
- A release merges `next` into `main` with a merge commit, so `main`'s history reads one stage at a time, then tags it.
- An urgent fix goes on a branch off `main`, is released as 0.N.y, and `main` is merged back into `next`.

Nothing is pushed straight to `main` or `next`. A GitHub ruleset enforces that, and a pre-push hook catches it before it gets that far.

## What's kept across versions

Earlier work has to stay usable. That's the whole point of building in stages.

- **Replays.** Every version of the viewer plays every replay ever recorded. The format only gains fields; a change that can't keep to that bumps the format version, and the loader keeps reading the old one. A sample replay from each released version stays in the repo to prove it.
- **Brains.** The observation and action layout only grows. New inputs and actions are added switched off or zero-weighted and turned on during training, so the previous stage's brain still loads. Each checkpoint records the schema version it was trained on, and loading one that doesn't fit fails with the reason.
- **Training runs.** Weights never go in git. Every run records the commit, config and parent it came from, and only runs from committed code can be promoted. The lineage file, `sim/brains.toml`, is the one place that says which brain each stage settled on.
- **The world (from 1.0).** The main world's state is saved apart from the brains, carries its own version, and is moved forward when that changes, never reset to fit new code.

## Making a release

When everything listed for the stage in the roadmap is on `next`, or has been moved to a later stage:

1. Everything since the last release passes the hooks' checks and CI.
2. The stage's promoted brain meets the stage's goal on its evals, and does no worse on every earlier stage's evals than the brain released with that stage.
3. The benchmark is no slower than at the last release, or the slowdown is written down with the reason.
4. Every sample replay, from every earlier version, plays in the viewer.
5. There's a clip of what the stage was for.
6. The roadmap, VISION.md and the changelog match what was built; the version is bumped in `viewer/package.json` (and the sim's `pyproject.toml` from 0.1).
7. The site matches the release: "Where it's at" in `site/index.md`, the hero still if the stage has a better one, and the replay it plays. Then it's rebuilt and deployed ([site.md](site.md)).

Then merge `next` into `main` by pull request, as a merge commit, and tag it.

## Changelog

Kept as we go: the top section, **Unreleased**, gets a few plain sentences from each branch before it's merged (what changed, what to watch for, anything a saved brain or replay needs). At release time it becomes the version's entry, checked against the commits on `next` since the last release (`git log --first-parent main..next`).
