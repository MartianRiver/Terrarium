# Local pet nursery

From `viewer/`, run `npm run dev -- --host 127.0.0.1 --port 5188 --strictPort`
and open `http://127.0.0.1:5188/pet.html`. This uses the existing viewer dependencies.
The pet entry is included in the normal local build, excluded from the public-site build.

Bring Nim home, then feed, play, offer attention and clean up. During ball play,
click somewhere in the garden to move the ball; Nim chases it autonomously.
Tap Nim itself for affection. Dragging orbits the camera; Garden view resets it.

Care saves under `terrarium.pet.v1` in this browser's local storage, scoped to the
origin (including port). It is a local pet on this browser, not a synced account.
Reopening advances needs through elapsed real time. The computer/server need
not run while closed; catch-up happens on return. Keeping the same URL matters.
Browser data deletion loses the save. A JSON download is available in About;
importing saves is not implemented yet.

## Care rules

All the numbers are in `RULES` at the top of `petcare.ts`; they're starting values to balance by playing.

- **Needs.** Fullness runs 100 to 0 in 10 h awake, so a full tummy is hungry (20) after 8 h: full at 07:30, hungry by 15:30. Happiness runs 100 to 0 in 10 h awake, 1.5x as fast while hungry and +0.2x per dropping (up to 6). A meal is +30 (refused above 85) and becomes a dropping after 30 min; droppings stay until cleaned. Play and attention have cooldowns.
- **Sleep.** Per pet (`bed`, `wake`, minutes after local midnight; default 20:00 to 07:30). Asleep its metabolism slows: fullness, happiness, the neglect clock and illness all move at a tenth of the day rate, so a night is safe. Feed, play and attention are refused with a kind message; cleaning and medicine still work.
- **Neglect, illness, death.** Neglect is any of: fullness 0, happiness 0, or a dropping left. The neglect clock counts awake time (a tenth while asleep) and resets when nothing is unmet. 4 h of it is "poorly", 8 h makes the pet ill. Ill and untreated for 12 h (6 h is "very ill") and it dies, so about 20 waking hours from the first unmet need: neglected from 10:00, it's ill by 18:00 and dies about 16:20 the next day. Feeding doesn't cure illness; medicine does, at once, and restarts the neglect clock. The wellbeing bar is derived: 100 down to 40 over the neglect clock, 40 down to 0 over the illness.
- **Death** is final for that pet: the garden empties, care is refused, and the page offers a new egg.
- **Catch-up.** `advance` steps from event to event (meals, bedtime and waking, a need crossing a threshold, the poorly/ill/dead marks), so 30 h away over a night takes a handful of steps, not a loop over every tick, and gives the same result as many short visits.
- **Saves** from the first prototype load with sleep and illness fields filled in (20:00 to 07:30, well).

`?debug` on the page URL adds buttons for +30 min, +1 h, +8 h and jumps to the next 20:00 or 07:30. They add to the saved `offset`, so they go through the same `advance` as real time.

`petcare.ts` owns persisted needs and deterministic elapsed-time integration.
`petworld.ts` emits scripted frames into the existing Three.js garden/WorldView
renderer; it also adds a toy and affection hearts. It does not run the Python
physics engine or a learned policy. Visual position/animation restart on reload;
needs, digestion, poop and the recent care journal persist. Pet actions are not
training results and do not modify checkpoints, worlds or the training queue.

`pet.ts` owns controls, local saves, error states and tab coordination. Unreadable
saves are preserved and do not get silently replaced. Storage-write failures stop
care until saving succeeds, with download available. Changes from another tab
stop care in this tab and request a reload. Simultaneous writes across tabs are
not transactionally locked; use one active care tab for this prototype.

Validation: `npm test -- petcare` checks offline/online equivalence, digestion,
cleanup, cooldowns, corrupt saves, backward-clock handling, sleeping through a night, a school day, illness, medicine and death. `npm run build`
checks the whole viewer. Browser interaction checks should use an isolated
profile so they do not affect an owner's pet.
