---
title: How this is made
description: Who does what on Terrarium: what I decide, what Claude Code does, and how the write-ups get made.
---

I build Terrarium with Claude Code, running Claude Opus (Opus 5.5 as I write this).

I set where it's going: the stages and what each one is for, what has to be true before one counts as done, and the rules. The big one is that nothing gets scripted into a brain that's carried forward: behaviour comes from rewards and costs, never hard-coded rules. When something stalls, I decide which way to go next.

Claude writes most of the code and scripts, runs the training and the tests on my Mac and on GPUs I rent by the hour, and reports back. I read the results, push back, and decide. Some of the turns that mattered were mine, like giving the Terrikins blocks they can grab and pull out of the way. Some were Claude's, like finding that a new action was firing on half of all training ticks, which is why no food ever made it home. Adversarial reviews of the code and the numbers catch what the day-to-day misses.

I've wanted a digital ant farm for a long time: something I could host online for people to watch over time. My first go, about two years ago, started from the very bottom, with walking, and I never got the animations working. The next try was an agar.io clone, to skip the walking problem altogether, but I had to redesign the game so much to make anything interesting happen that it never suited this, and it needed a lot of compute before it showed anything that made more compute and time feel worth spending. So this time I skipped real walking and went straight for the creature, something between a bee and an ant. Ants and bees, with their scent trails, their dances and their hive minds, are incredible animals, and I think we're finally at the point where we can grow some odd alien hybrid of them digitally, and faithfully: nothing scripted, no cheating the mind into looking clever.

A pet project like this only fits in the time I have because of agentic coding. The grunt work, all the scripting, and setting up and minding rented GPUs would otherwise take more hours than I've got.

## The notes

The notes are drafted by Claude from the run records and edited by me. Each one says which model drafted it. Every number in them comes from a run record, and I read every post and clip before it goes up. They're in my voice, so when a note says "I", that's me.
