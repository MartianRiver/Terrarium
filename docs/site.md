# The site

terrarium.martianriver.com is a front page, the notes, and the viewer at `/watch/`. Everything is static: no framework, no analytics, no cookies.

| | |
|---|---|
| `site/index.md` | the front page's text: what it is, where it's at, what's next; the latest notes go where `<!-- notes -->` is |
| `site/how.md` | /how/, who does what: what I decide and what the model I build with does |
| `site/notes/` | published posts, `YYYY-MM-DD-slug.md`, served at `/notes/slug/` |
| `site/clips.json` | every clip a post can show, and where it's cut from |
| `site/site.css`, `hero.jpg`, `card.jpg` | the look, the front page's still, the link preview image |
| `site/fonts/` | Nunito, served from the site itself, with its licence (SIL OFL) |
| `viewer/site.mjs` | turns those into pages |

```
cd viewer
npm run site        # dist-site/: the viewer in watch/, the pages beside it
```

Deploying is an rsync of `dist-site/` to the web server. Anything unfinished in a page or a published post, like a draft marker or a note of what's still to write (the same list the commit checks refuse), stops `npm run site`, which deletes what it had built so a half-made site can't be deployed. A review build still shows it. Old links like `/?replay=…&follow` are sent on to `/watch/` with their query.

## Posts

A post starts with a few lines of front matter:

```
---
title: Clover: one Terrikin learns to eat
date: 2026-10-23T17:00+11:00
written: 2026-10-25
summary: One line for the list of notes and link previews.
stage: 0.2 Clover
clips: clover-gen0, clover-final
drafted: the exact model that drafted it
edited: River James
---
```

`date` is when it happened, or when it went up on Instagram, and orders the notes: a day, or a time with its offset (one a day at 5 PM Sydney time, like the Instagram posts); pages show the day in Sydney time. `written` is when the post was written, and shows in the byline when it's a different day. `drafted` and `edited` are required too, and show under the date as a byline linking to /how/. Posts are in my voice: the "I" is me.

Then Markdown. The deeper stuff goes in folds, which also read fine on GitHub:

```
<details>
<summary>The numbers</summary>

| ... |

</details>
```

## Drafts and review

Drafts never go in git. They live in a folder outside the repo (mine is my backups folder's `terrarium/site/drafts`), named by `SITE_DRAFTS`, or `site/drafts/`, which is ignored. Publishing a post means moving it into `site/notes/`. `npm run site` never reads drafts.

```
SITE_DRAFTS=... SITE_CLIPS=... npm run review     # dist-review/: the site with the drafts in
npm run review:serve                              # on the local network, port 5198, for reading on a phone
```

A review copy looks exactly like the published site, and tells search engines to stay out (`noindex` and a `robots.txt`). `npm run review -- --marked` also puts a bar across the top, DRAFT on each draft, and where each clip came from under it.

## Clips

Clips stay out of the repo. `site/clips.json` names each one's master by its path in the clips backups folder, with where to start, how long, how wide and an optional crop (ffmpeg's `w:h:x:y`). The build cuts them with ffmpeg from `SITE_CLIPS` into small muted H.264 loops with a poster frame, and caches them by their settings. A post shows one with `{{clip name}}`, and its front matter's `clips:` has to list exactly the ones it shows, or the build stops.

Longer videos go on YouTube, unlisted: `{{youtube VIDEO_ID Title}}` shows a button, and nothing loads from YouTube until it's pressed.
