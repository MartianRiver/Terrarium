# Versions and releases

## Version numbers

`0.N.y` until the main world runs, then 1.0.

- **0.N.0** opens stage N with its first milestone. The stages and their milestones are in [ROADMAP.md](../ROADMAP.md).
- **0.N.y** is the stage's next milestone, or a fix. A milestone can bring anything: new mechanics, new inputs or actions, retrained brains.
- A stage is finished when its last milestone ships. That's said on the site and dated in the roadmap; the number doesn't change for it.
- If `main` falls a month behind `next`, a release goes out at the next green CI anyway, named for what's in it.

Each release is a tag (`v0.4.0`) with an entry in [CHANGELOG.md](../CHANGELOG.md).

Until 0.4, a version was a whole stage, and 0.N.y couldn't retrain or add anything. Stages turned out to be weeks of work, so finished work sat in `next` for weeks (69 commits by 7 November 2026).

## Branches

- `main` is the last release and nothing else. It only moves when a milestone is released.
- `next` is the work in progress. Each piece of work is a branch off `next`, squash-merged back by a pull request once its checks pass: the commit hooks, a read of the whole diff, and from 0.1 the CI checks and a benchmark no slower than the baseline (or the slowdown explained in the PR).
- A release merges `next` into `main` with a merge commit, so `main`'s history reads one release at a time, then tags it.
- An urgent fix goes on a branch off `main`, is released as 0.N.y, and `main` is merged back into `next`.

Nothing is pushed straight to `main` or `next`. A GitHub ruleset enforces that, and a pre-push hook catches it before it gets that far.

## What's kept across versions

Earlier work has to stay usable. That's the whole point of building in stages.

- **Replays.** Every version of the viewer plays every replay ever recorded. The format only gains fields; a change that can't keep to that bumps the format version, and the loader keeps reading the old one. A sample replay from each released version stays in the repo to prove it.
- **Brains.** The observation and action layout only grows. New inputs and actions are added switched off or zero-weighted and turned on during training, so the previous stage's brain still loads. Each checkpoint records the schema version it was trained on, and loading one that doesn't fit fails with the reason.
- **Training runs.** Weights never go in git. Every run records the commit, config and parent it came from, and only runs from committed code can be promoted. The lineage file, `sim/brains.toml`, is the one place that says which brain each stage settled on.
- **Formats.** Each file kind carries its own version, bumped only when it changes in a way the old reader can't take:

  | format | version | where | bumped when |
  |---|---|---|---|
  | replay | 2 | `sim/terrarium/replay.py`, `viewer/src/replay.ts` | a field is renamed, removed or changes meaning or type ([replays.md](replays.md)) |
  | brain schema | 21 | `sim/terrarium/schema.py` | every new input or action (append only; older brains load) |
  | mind track | 1 | `sim/terrarium/mind.py` | as replays |
  | worker | 13 | `sim/terrarium/worker.py` | the worker and the coordinator stop understanding each other |
  | scoring | none yet | | #115 made every game its own world, so scores from before it can't be compared game for game with scores after; a version written into every score file would say so |

- **The world (from 1.0).** The main world's state is saved apart from the brains, carries its own version, and is moved forward when that changes, never reset to fit new code.

## Making a release

When a milestone's done-when holds on `next` (on a fresh block of seeds, per [evals.md](evals.md)):

1. Everything since the last release passes the hooks' checks and CI.
2. The milestone's brain meets its done-when. When the recommended colony brain changes, it also does no worse on every earlier stage's evals than the brain it replaces.
3. The benchmark is no slower than at the last release, or the slowdown is written down with the reason.
4. Every sample replay, from every earlier version, plays in the viewer, and a new sample goes in whenever the replay format changed.
5. There's a clip of what the milestone was for.
6. The roadmap, VISION.md and the changelog (with `changes/` folded in) match what was built; the version is bumped in `viewer/package.json` (and the sim's `pyproject.toml` from 0.1).
7. The site matches the release: "Where it's at" in `site/index.md`, the hero still if the stage has a better one, and the replay it plays. Then it's rebuilt and deployed ([site.md](site.md)).

Then merge `next` into `main` by pull request, as a merge commit, and tag it.

## Changelog

Kept as we go, a file a branch: each branch writes its few plain sentences (what changed, what to watch for, anything a saved brain or replay needs) in `changes/<branch>.md`, and never edits CHANGELOG.md itself, so two branches open at once never conflict over its top. The **Unreleased** section holds what was written there before this started.

At release time the fragments are folded into Unreleased in the order they landed on `next`, and deleted:

```
git log --reverse --diff-filter=A --format= --name-only main..next -- changes/
```

Unreleased then becomes the version's entry, checked against the commits on `next` since the last release (`git log --first-parent main..next`).
