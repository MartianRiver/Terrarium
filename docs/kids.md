# Catch them!

A game of tag for children against a tag brain's Terrikins. You're always it, with a ring under you, and faster than them; touch one and it's a catch: it gets knocked away with a boing, spins dizzy under a ring of stars for a moment, and can't be caught again straight away, so you go after another. A round is 90 seconds. Nothing needs reading: pictures to pick a game, a star count, a bar running down, and at the end your catches, the stars they earned, your best, and one big button to go again.

It runs on one machine at home, the game and the viewer both, against a brain on disk. Nobody else can reach it: the server listens on that machine only.

## The games

- **Little**: the tag nursery's room, 12 m with two pillars, six runners, everyone in sight at once. Made for a five-year-old.
- **Big**, in five levels: the room with sixteen blocks to hide behind (`nursery-tag-hide.toml`), six runners, and a sprint. Each level gives you a little less: less speed over the runners, a smaller reach, runners that slow down less when you're struggling; the fifth is the 20 m playground. The camera follows you a little closer in. For older children.

Every round earns up to three stars: one for any catch, two and three for the level's targets, set at about 45% and 80% of what a sloppy pretend player catches (below). Two stars on a level opens the next. The stars light up along the top as they're earned, and the end screen says when a level opened.

Every game watches how it's going. A while without a catch (5 s in little, 6–8 in big) slows the runners a little every second, down to the level's floor; quick catches speed them back up. So a round settles where catches keep coming without being free. The settings are `MODES` in `sim/terrarium/kids.py`.

You can be a Terrikin, a panda or a baby dragon (horns, spikes down its back, little wings that flap as it walks, and a roar for a honk): the faces under the pictures.

## Controls

| | mouse or trackpad | keys | gamepad (Xbox layout) |
|---|---|---|---|
| walk | point: you walk to wherever the pointer is, no button to hold | arrows or WASD, by the screen | left stick or d-pad |
| sprint (big) | click | Space or Shift | A or right trigger |
| honk | | H | X or B |
| turn the camera | | Q and E | right stick, left and right |
| zoom | | | right stick up and down, or the bumpers |
| camera back | | | Y |
| pause | | P | Menu (A, a click or any key goes on) |
| back to the pictures | the small ✕ | Esc | View, while paused |

On the picture screens, left and right choose (Little, then each open level of Big), and Enter, Space or A starts; X or B goes to the next costume. Keys or a stick take over from the pointer until the mouse moves again, since on a laptop the cursor is always somewhere over the room. A game goes fullscreen when it starts (`?window` keeps it in the window), and pauses itself if the window's hidden. A gamepad buzzes at every catch, where the browser can make it.

## Setting it up on Windows

Once, from a copy of the repo (`git clone`, or GitHub's Download ZIP):

```
powershell -ExecutionPolicy Bypass -File kids\setup.ps1
```

That installs uv and Node if they're missing (uv's own installer, Node through winget), sets up the sim with torch for the CPU (`uv sync --extra cpu`), builds the viewer, makes `%USERPROFILE%\terrarium-kids` for the games kept, and puts a **Catch them!** shortcut on the desktop. Copy the runner brain to `%USERPROFILE%\terrarium-kids\brain.pt`. Then the shortcut (`kids\play.cmd`) starts the server and opens the game in the browser; closing its window stops it.

Integrated graphics are fine. If it stutters, add `--lite` to the command in `play.cmd`: 30 frames a second, no shadows or antialiasing.

## Anywhere else

```
cd sim && uv sync            # on Linux: uv sync --extra cpu, and --extra cpu on every uv run
cd viewer && npm ci && npm run build
cd sim && uv run python -m terrarium.kidsserve --brain PATH/TO/brain.pt --keep ~/terrarium-kids --open
```

It's at `http://127.0.0.1:5195/` (`--port` for another). The brain played so far is the best runner of the hearing seeds in the 0.4 notes (tag among sixteen blocks, with hearing, seed 1, 16M), the one tagged least by the all-knowing chaser.

For working on it: `npm run dev` in `viewer/` proxies `/api/kids` to the kids server on 5195, so the page is at `/kids.html` on the dev server.

## What's kept

Every game, in `--keep`: its replay (`<date>/<time>-<mode><level>-<seed>.jsonl.gz`, everyone's every tick, yours included, and the level's settings in its source) and a line in `plays.jsonl`: when, the mode and level, how long it was played, why it stopped (`over`, `again`, `home`, `quit` for a page closed, `idle` after half an hour without a step, `stopped` for the server stopping), the catches and when each came, the runners' pace at each, and whether a mouse, a finger, keys or a gamepad steered. `GET /api/kids` returns the last twenty lines. Stars, levels and the costume are kept in the browser.

That's for learning how long each game holds a child and where it gets too hard or too easy, and later for scoring brains against how children play. It never trains the brain we carry forward.

## Balancing it

Two pretend players stood in for children while tuning it: a greedy one that always goes straight for the nearest catchable runner, and a sloppy one that picks a target every 0.6 s, aims off by a random amount and dawdles now and then. The numbers are in the 0.4 notes ("Catch them!").
