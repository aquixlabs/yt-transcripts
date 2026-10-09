"""
Optional live check: one public video, from this machine, free. Never calls Apify.
Not part of the offline suite (the file name does not start with test_).

    YT_LIVE=1 python tests/live_smoke.py

Exit 0 on OK. On a home connection anything else is a real failure. From a
cloud server BLOCKED or RATE_LIMITED is the expected, honest answer, so it
exits 3 rather than 1.
"""
import os
import sys

import yt_transcripts as yt

VIDEO = "GJLlxj_dtq8"      # upstream's own test video: public, manual English captions


def main():
    if os.environ.get("YT_LIVE") != "1":
        print("skipped: set YT_LIVE=1 to run (one request burst to YouTube, no Apify)")
        return 0
    os.environ.pop("APIFY_TOKEN", None)
    r = yt.get_transcript(VIDEO, ["en"])
    print(f"[{r.status}] {VIDEO} lang={r.language_code} generated={r.is_generated} "
          f"segments={len(r.segments or [])} chars={len(r.text or '')} {r.detail}")
    if r.ok:
        print("first segment:", r.segments[0])
        return 0
    return 3 if r.status in (yt.BLOCKED, yt.RATE_LIMITED) else 1


if __name__ == "__main__":
    sys.exit(main())
