# Where each fixture comes from

`tools/build_fixtures.py` rebuilds all of them, offline, from youtube-transcript-api's
installed test assets (MIT, Jonas Depoix; see `NOTICE`).

## Recorded: real YouTube responses captured by the upstream project

Each one is trimmed to `playabilityStatus`, `videoDetails` (`videoId`, `title`) and `captions`,
the only keys the classifier reads.

| fixture | upstream asset | expected status |
|---|---|---|
| `player_ok.json` | `youtube.innertube.json.static` | OK |
| `player_no_captions.json` | `youtube_transcripts_disabled.innertube.json.static` | NO_CAPTIONS |
| `player_no_captions2.json` | `youtube_transcripts_disabled2.innertube.json.static` | NO_CAPTIONS |
| `player_age_restricted.json` | `youtube_age_restricted.innertube.json.static` | AGE_RESTRICTED |
| `player_bot_check.json` | `youtube_request_blocked.innertube.json.static` | BLOCKED |
| `player_unavailable.json` | `youtube_video_unavailable.innertube.json.static` | REMOVED |
| `player_unplayable_custom.json` | `youtube_unplayable.innertube.json.static` | ERROR (unknown reason) |
| `player_po_token.json` | `youtube_po_token_required.innertube.json.static` | BLOCKED |
| `watch_captcha.html` | `youtube_too_many_requests.html.static` (untrimmed) | BLOCKED |
| `transcript.xml` | `transcript.xml.static` | OK |

## Synthesized: a recorded shape with one thing changed

| fixture | built from | change | why |
|---|---|---|---|
| `player_private.json` | unplayable | reason "This video is private" | no recorded private response is available |
| `player_members_only.json` | unplayable | members-only reason | same |
| `player_geo_blocked.json` | unplayable | "Video unavailable" + "not made this video available in your country" | a geo block must not read as REMOVED |
| `player_degraded.json` | n/a | status OK, nothing else | the refusal shape most often misread as "no captions" |
| `player_wrong_video.json` | no_captions | `videoId` changed | an answer about another video is not an answer |
| `player_tracks_no_url.json` | ok | every `baseUrl` removed | tracks listed with their URLs withheld |
| `watch.html` | n/a | minimal page, placeholder `INNERTUBE_API_KEY` | the real page is 1 MB; only the key is read |
| `transcript_empty.xml` | n/a | empty `<transcript>` | how a refused track request often looks |

HTTP 403, 429 and 500 answers and network errors are produced by `tests/fakeyt.py`.
