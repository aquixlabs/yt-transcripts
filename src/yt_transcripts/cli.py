"""
yt-transcripts VIDEO_OR_CHANNEL... [--lang en,de] [--json] [--apify]

Exit codes: 0 every input OK · 1 at least one input not OK · 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, get_transcripts
from .apify import DEFAULT_MAX_CHARGE_USD, DEFAULT_MAX_VIDEOS


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yt-transcripts",
        description="YouTube transcripts with an honest status: a block is never "
                    "reported as 'no captions'.")
    p.add_argument("inputs", nargs="+", metavar="VIDEO",
                   help="video ID or URL; with --apify also @handle, channel or playlist URL")
    p.add_argument("--lang", default="en",
                   help="language codes in order of preference, comma-separated (default: en)")
    p.add_argument("--json", action="store_true",
                   help="print one JSON object per input (status, text, segments, ...)")
    p.add_argument("--apify", action="store_true",
                   help="PAID, on your own APIFY_TOKEN: retry BLOCKED/RATE_LIMITED videos and "
                        "fetch channels/playlists through the aquixlabs Apify actor")
    p.add_argument("--max-videos", type=int, default=DEFAULT_MAX_VIDEOS,
                   help=f"--apify: videos per channel/playlist (default {DEFAULT_MAX_VIDEOS})")
    p.add_argument("--max-charge", type=float, default=DEFAULT_MAX_CHARGE_USD,
                   help=f"--apify: spend cap for the run in USD (default {DEFAULT_MAX_CHARGE_USD:.2f})")
    p.add_argument("--version", action="version", version=f"yt-transcripts {__version__}")
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    langs = [x.strip() for x in args.lang.split(",") if x.strip()] or ["en"]
    results = get_transcripts(args.inputs, langs, apify=args.apify,
                              max_videos=args.max_videos, max_charge_usd=args.max_charge)
    for r in results:
        if args.json:
            print(json.dumps(r.to_dict(), ensure_ascii=False))
            continue
        label = r.video_id or r.input or "?"
        line = f"[{r.status}] {label}"
        if r.language_code:
            line += f" ({r.language_code}{', auto' if r.is_generated else ''})"
        if r.source != "local":
            line += f" via {r.source}"
        if r.detail:
            line += f": {r.detail}"
        print(line, file=sys.stderr)
        if r.hint:
            print(f"  hint: {r.hint}", file=sys.stderr)
        if r.ok:
            print(r.text)
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
