---
name: yt-transcripts
description: Fetch YouTube video transcripts (captions/subtitles) with an honest status. Use when the user wants what a YouTube video says, a summary or quotes from it, or transcripts for several videos, a channel or a playlist. Never tells a block apart from "no captions" wrongly.
---

# yt-transcripts

Fetch transcripts with the `yt-transcripts` CLI (install: `pip install "git+https://github.com/aquixlabs/yt-transcripts"`).

```bash
yt-transcripts --json VIDEO_ID_OR_URL [MORE ...] [--lang en,de]
```

Each line of output is one JSON object. Read `status` first:

| status | what to tell the user |
|---|---|
| `OK` | Use `text` (and `segments` for timestamps, in seconds). |
| `NO_CAPTIONS` | The video has no captions. This is a fact about the video. |
| `BLOCKED` | YouTube refused this machine. **Do not say the video has no captions.** |
| `RATE_LIMITED` | Too many requests from this machine. Try again later. |
| `AGE_RESTRICTED` / `PRIVATE` / `REMOVED` | The video can't be read. Say which. |
| `LANGUAGE_UNAVAILABLE` | Offer the codes in `available_languages` and retry with `--lang`. |
| `ERROR` | Report `detail`. Don't guess. |

## Rules

1. **A `BLOCKED` or `RATE_LIMITED` result is never "no captions".** Tell the user YouTube refused
   the request, and show the `hint`.
2. **`--apify` costs the user money.** It retries refused videos, and fetches channels and
   playlists (`@handle`, `/channel/...`, `playlist?list=...`), through the paid aquixlabs Apify
   actor on the user's own `APIFY_TOKEN`. Ask before using it, mention that it's paid per
   transcript, and set a cap: `--max-charge 0.25 --max-videos 10`.
3. Long transcripts: summarise them, or work through them in parts. Don't paste them whole.
4. Respect YouTube's terms and creators' rights: quote briefly and give credit.

## Examples

```bash
yt-transcripts --json https://youtu.be/dQw4w9WgXcQ
yt-transcripts --json dQw4w9WgXcQ --lang es,en
yt-transcripts --json @somechannel --apify --max-videos 10 --max-charge 0.25   # only after the user agrees
```
