# The site

terrarium.martianriver.com is a front page, a blog, a gallery of brains at `/brains/`, a page for lending a GPU at `/at-home/`, and the viewer at `/watch/`. Everything is static: no framework, no analytics, no cookies.

| | |
|---|---|
| `site/index.md` | the front page's text: what it is, where it's at, what's next; the latest posts go where `<!-- posts -->` is |
| `site/how.md` | /how/, who does what: what I decide and what the model I build with does |
| `site/blog/` | published posts, `YYYY-MM-DD-slug.md`, served at `/blog/slug/` (the blog was called notes at first, so `/notes/…` forwards there) |
| `site/clips.json` | every clip a post can show, and where it's cut from |
| `site/site.css`, `hero.jpg`, `card.jpg` | the look, the front page's still, the link preview image |
| `site/fonts/` | Nunito, served from the site itself, with its licence (SIL OFL) |
| `site/gallery.toml` | the gallery's steps, their captions, what's being worked on beside the line, and side experiments |
| `viewer/site.mjs` | turns those into pages |

```
cd viewer
npm run site        # dist-site/: the viewer in watch/, the pages beside it
```

Deploying is an rsync of `dist-site/` to the web server, leaving out `replays/gallery/` (published on its own, below). Anything unfinished in a page or a published post, like a draft marker or a note of what's still to write (the same list the commit checks refuse), stops `npm run site`, which deletes what it had built so a half-made site can't be deployed. A review build still shows it. Old links like `/?replay=…&follow` are sent on to `/watch/` with their query.

## Posts

A post starts with a few lines of front matter:

```
---
title: Clover: one Terrikin learns to eat
date: 2026-10-23T17:00+11:00
written: 2026-10-25
summary: One line for the list of posts and link previews.
stage: 0.2 Clover
clips: clover-gen0, clover-final
drafted: the exact model that drafted it
edited: River James
---
```

`date` is when it happened, or when it went up on Instagram, and orders the posts: a day, or a time with its offset (one a day at 5 PM Sydney time, like the Instagram posts); pages show the day in Sydney time. `written` is when the post was written, and shows in the byline when it's a different day. `drafted` and `edited` are required too, and show under the date as a byline linking to /how/. Posts are in my voice: the "I" is me.

Then Markdown. The deeper stuff goes in folds, which also read fine on GitHub:

```
<details>
<summary>The numbers</summary>

| ... |

</details>
```

## Drafts and review

Drafts never go in git. They live in a folder outside the repo (mine is my backups folder's `terrarium/site/drafts`), named by `SITE_DRAFTS`, or `site/drafts/`, which is ignored. Publishing a post means moving it into `site/blog/`. `npm run site` never reads drafts.

```
SITE_DRAFTS=... SITE_CLIPS=... npm run review     # dist-review/: the site with the drafts in
npm run review:serve                              # on the local network, port 5198, for reading on a phone
```

A review copy looks exactly like the published site, and tells search engines to stay out (`noindex` and a `robots.txt`). `npm run review -- --marked` also puts a bar across the top, DRAFT on each draft, and where each clip came from under it.

## Clips

Clips stay out of the repo. `site/clips.json` names each one's master by its path in the clips backups folder, with where to start, how long, how wide and an optional crop (ffmpeg's `w:h:x:y`). The build cuts them with ffmpeg from `SITE_CLIPS` into small muted H.264 loops with a poster frame, and caches them by their settings. A post shows one with `{{clip name}}`, and its front matter's `clips:` has to list exactly the ones it shows, or the build stops.

Longer videos go on YouTube, unlisted: `{{youtube VIDEO_ID Title}}` shows a button, and nothing loads from YouTube until it's pressed.

## The gallery of brains

`/brains/` starts with what's being worked on beside the main line (each `[[working]]` in `site/gallery.toml`: what it's for, then its best few finished runs by the number that says how close it is, `score`, each with a note on what it tried, matched by run name), then lists every brain the one training now came from, back to the first, grouped into the steps `site/gallery.toml` names, then the newest brains of the training going on now, then a few side experiments. Each has a Watch link, and a replay opened from there gets a bar to step to the brain before or after it. The numbers are each run's own evals, in the world it trained in.

The page is static and reads `/replays/gallery/index.json` when it opens. That and the replays come from

```
cd sim
uv run python -m terrarium.gallery OUT --line 'pbt-t*'
```

which traces the lineage from the best scored run of the line being trained (`--line`, matched against run names), records a 3-minute replay of each brain in its own world (seed 0, the same as the runs page), and writes OUT/index.json. While training runs, it's rebuilt and synced to the server's `replays/gallery/` every 15 minutes, so the newest brains show up without redeploying the site. A review build shows a local one with `SITE_GALLERY=OUT`.

## Terrarium at Home

`/at-home/` is `site/at-home.md` (what the worker does, installing it, its versions) with two things put in where it has `<!-- reviews -->` and `<!-- board -->`.

Reviews: each file in `site/reviews/` is one model's review of the worker's code, pasted in whole, with `model`, `date`, `commit` (the code it read), `verdict` (one line for the list) and an optional `link` to the conversation in its front matter. Each gets its own page at `/at-home/reviews/<file>/`. Under them, the prompt a reader can paste into a new chat to check the code themselves. With no reviews, only the prompt shows.

The board is read live from the job queue's public `/api/board` (cached for 30 s) when the page opens. What lent machines trained is priced at what rented GPUs have cost per sample, from the page's front matter (`usd_per_billion`, where it came from, and the AUD rate and its date), so update those when the ledger moves.
