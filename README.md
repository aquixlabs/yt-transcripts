# yt-transcripts

**YouTube transcripts for AI agents, with a status you can trust.**

When YouTube blocks a request, most transcript tools tell you the video has no captions.
Your agent believes them and moves on. yt-transcripts doesn't do that. Every answer comes with
a status, and a block is never reported as "no captions".

One codebase gives you a Python package, a CLI, an MCP server (Claude, Cursor and others)
and an agent skill.

```
$ yt-transcripts https://youtu.be/GJLlxj_dtq8
[OK] GJLlxj_dtq8 (en)
Hey, how's it going Dave 2d here? ...

$ yt-transcripts dsMFmonKDD4            # from a cloud server
[BLOCKED] dsMFmonKDD4: YouTube asked this machine to sign in to prove it is not a bot
  hint: YouTube refused this machine. Retry from a home connection, or set APIFY_TOKEN ...
```

## Why

Three problems keep coming up in the issue trackers of the popular transcript tools:

1. **Cloud IPs get blocked.** It works on your laptop and fails on the server.
2. **One video at a time.** No channels, no playlists.
3. **"Blocked" shows up as "no captions".** A refused request looks like a video without
   subtitles, so the agent gets a wrong answer and nothing says so.

yt-transcripts fixes the third problem itself and gives you a way out of the first two.

## Statuses

Every result has exactly one of these:

| status | what it means | retry? |
|---|---|---|
| `OK` | Transcript fetched: `text`, timed `segments` and `language_code`. | no |
| `NO_CAPTIONS` | YouTube served the video, and it really has no captions. | no |
| `BLOCKED` | YouTube refused this machine (bot check, captcha, 403, geo-block, empty or withheld tracks). **It does not mean the video has no captions.** | yes, from elsewhere |
| `RATE_LIMITED` | HTTP 429: too many requests from this IP. | yes, later |
| `AGE_RESTRICTED` | Needs a signed-in, age-verified account. | no |
| `PRIVATE` | Private or members-only. | no |
| `REMOVED` | Deleted or terminated, or the ID never existed. | no |
| `LANGUAGE_UNAVAILABLE` | Captions exist, but not in the languages you asked for. `available_languages` lists what does exist. | with other languages |
| `ERROR` | Something we can't classify honestly: the network is down, or YouTube changed something. `detail` says what. | yes |

**How NO_CAPTIONS stays honest.** When YouTube refuses a request, it often sends back a player
response with no captions block. To most tools that looks the same as a video with captions
turned off. yt-transcripts reports `NO_CAPTIONS` from exactly one place in the code, and only
after checking that YouTube actually served the video it was asked about: playability `OK`, the
right `videoDetails.videoId`, and no caption tracks listed. If any of those checks fails, the
result is `BLOCKED`, and `detail` says why.

## Install

```bash
pip install "git+https://github.com/aquixlabs/yt-transcripts"          # CLI + Python
pip install "yt-transcripts[mcp] @ git+https://github.com/aquixlabs/yt-transcripts"   # + MCP server
```

Needs Python 3.9 or newer (the MCP server needs 3.10 or newer). Tested on 3.13.

## Use it

### CLI

```bash
yt-transcripts dQw4w9WgXcQ                         # prints the text; status goes to stderr
yt-transcripts https://youtu.be/dQw4w9WgXcQ --lang de,en
yt-transcripts VIDEO1 VIDEO2 --json                # one JSON object per video
yt-transcripts @somechannel --apify --max-videos 10 --max-charge 0.25   # paid, see below
```

Exit code: `0` if every input is `OK`, `1` if any input isn't, `2` for a usage error.

### Python

```python
from yt_transcripts import get_transcript, get_transcripts

r = get_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ", languages=["en"])
if r.ok:
    print(r.text)
    print(r.segments[0])          # {"start": 0.0, "duration": 1.54, "text": "..."}
elif r.retryable:
    print("YouTube refused us, not the video:", r.status, r.detail, r.hint)
else:
    print("A fact about the video:", r.status)

results = get_transcripts(["VIDEO_ID_1", "VIDEO_ID_2"])
r.to_dict()                       # JSON-ready, includes "retryable"
```

### MCP server (Claude Desktop, Claude Code, Cursor)

It has two tools. `get_transcript` takes one video and splits long transcripts into pages
(`offset` / `next_offset`), so a three-hour video doesn't flood the context window.
`get_transcripts` takes several videos, channels or playlists.

Claude Desktop (`claude_desktop_config.json`) or Cursor (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "yt-transcripts": {
      "command": "yt-transcripts-mcp",
      "env": { "APIFY_TOKEN": "optional, only for the paid handoff" }
    }
  }
}
```

Claude Code:

```bash
claude mcp add yt-transcripts -- yt-transcripts-mcp
```

If the command isn't on the PATH your client uses, give the full path (`which yt-transcripts-mcp`).

### Agent skill

`skill/yt-transcripts/SKILL.md` teaches an agent to use the CLI and read the statuses
correctly. Copy the folder into your agent's skills directory (for Claude Code:
`~/.claude/skills/`).

## Blocked, or a whole channel: the optional Apify handoff

> **Disclosure: the handoff uses our own product.** `aquixlabs/youtube-channel-scraper` is an
> Apify actor made by the same people as this tool, and it is **paid per transcript**. It runs
> on **your** Apify account with **your** `APIFY_TOKEN`, so the charges are yours. We earn from
> it. The free local path works without it, and always will.

**When it's used:** only when you ask for it (`--apify`, `apify=True`, or `use_apify=True` in
MCP) **and** `APIFY_TOKEN` is set. Having a token in your environment doesn't count as asking.
Even then, it's only used for videos that came back `BLOCKED` or `RATE_LIMITED`, and for
channels and playlists. Without a token you get the honest status plus a one-line hint.

**What it costs:** at the time of writing, $3 to $5 per 1,000 transcripts depending on your
Apify plan, plus $0.50 per 1,000 videos. Videos that fail or are filtered out cost nothing. Check
the [actor page](https://apify.com/aquixlabs/youtube-channel-scraper) for current prices.
Apify's free plan includes $5 of usage a month.

**Spend cap:** every run is started with a cap (`--max-charge`, default **$0.50**). The actor
stops before reaching it and doesn't charge for what it skipped. Skipped videos come back as
`ERROR` with the reason; nothing disappears silently. If a run takes longer than 10 minutes,
yt-transcripts aborts it so it stops spending.

Results from the handoff carry `"source": "apify"` and the same statuses.

## Honest limits

- **The free local path breaks whenever YouTube changes.** It relies on
  [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api), which is usually
  fixed quickly. When YouTube changes something we don't recognise, you get `ERROR`, not a guess.
- **From cloud servers, expect `BLOCKED`.** YouTube blocks most datacenter IPs. This tool tells
  you so honestly; it doesn't get around the block. The handoff does, and it's paid.
- **Age-restricted, private and members-only videos aren't fetched** by either path. There is no
  sign-in support.
- **Channels and playlists go through the paid handoff only** in this version.
- **No translation.** You get the caption tracks YouTube has, in the languages you ask for.
- **`NO_CAPTIONS` is as reliable as YouTube's own answer.** The check proves YouTube served the
  video, not that YouTube will never add captions later.
- **One request at a time, no retries.** Retrying is up to you: `retryable` tells you when it
  makes sense.

## Respect YouTube and creators

This tool reads captions that YouTube makes publicly available. You're responsible for how you
use it. Follow [YouTube's Terms of Service](https://www.youtube.com/t/terms), respect creators'
copyright and rights in their work, and don't republish transcripts as your own. Keep request
rates reasonable.

## Credits

The fetching is done by [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
by Jonas Depoix and contributors (MIT). Several test fixtures are that project's recorded YouTube
responses, used under its MIT licence; see `NOTICE` and `tests/fixtures/SOURCES.md`.
yt-transcripts adds the status classification, the CLI, the MCP server, the skill and the handoff.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[mcp]"
.venv/bin/python -m unittest discover -s tests       # offline, no network, no Apify
.venv/bin/python tools/mutation_check.py             # proves each status test can fail
YT_LIVE=1 .venv/bin/python tests/live_smoke.py       # optional: one public video, free
```

## License

MIT. See `LICENSE`.
