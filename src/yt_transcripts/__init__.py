"""
yt-transcripts: YouTube transcripts for AI agents, with a status you can trust.

    from yt_transcripts import get_transcript
    r = get_transcript("https://youtu.be/dQw4w9WgXcQ")
    r.status   # "OK", "NO_CAPTIONS", "BLOCKED", "RATE_LIMITED", ...
    r.text, r.segments, r.language_code

Fetching is done by youtube-transcript-api (MIT, Jonas Depoix).
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from . import apify as _apify
from .core import (AGE_RESTRICTED, BLOCKED, ERROR, HINT_NO_TOKEN, HINT_WITH_TOKEN,
                   LANGUAGE_UNAVAILABLE, NO_CAPTIONS, OK, PRIVATE, RATE_LIMITED, REMOVED,
                   RETRYABLE, STATUSES, TranscriptResult, fetch_local, is_collection,
                   parse_video_id)

__version__ = "0.1.0"
__all__ = ["get_transcript", "get_transcripts", "TranscriptResult", "parse_video_id",
           "is_collection", "STATUSES", "RETRYABLE", "OK", "NO_CAPTIONS", "BLOCKED",
           "RATE_LIMITED", "AGE_RESTRICTED", "PRIVATE", "REMOVED", "LANGUAGE_UNAVAILABLE",
           "ERROR"]

HANDOFF = (BLOCKED, RATE_LIMITED)
HINT_COLLECTION = ("Channels and playlists are fetched through the aquixlabs Apify actor: set "
                   "APIFY_TOKEN and use --apify (Python: apify=True). Paid per transcript; see README.")


def _hint(result: TranscriptResult) -> TranscriptResult:
    if result.status in HANDOFF and not result.hint:
        result.hint = HINT_WITH_TOKEN if _apify.token_from_env() else HINT_NO_TOKEN
    return result


def get_transcript(video: str, languages: Iterable[str] = ("en",), *, apify: bool = False,
                   apify_token: Optional[str] = None,
                   max_charge_usd: float = _apify.DEFAULT_MAX_CHARGE_USD,
                   http_client=None) -> TranscriptResult:
    """
    One video's transcript, always with a status. Never raises for YouTube's
    answers; raises ValueError only when `video` is not a video ID or URL.

    `apify=True` retries a BLOCKED or RATE_LIMITED result through the aquixlabs
    Apify actor on your own APIFY_TOKEN (paid per transcript, capped at
    `max_charge_usd`). Without it, such a result carries a one-line hint.
    """
    vid = parse_video_id(video)
    langs = list(languages) or ["en"]
    result = fetch_local(vid, langs, http_client=http_client)
    if vid != video.strip():
        result.input = video
    if result.status not in HANDOFF or not apify:
        return _hint(result)
    token = apify_token or _apify.token_from_env()
    if not token:
        result.hint = HINT_NO_TOKEN
        return result
    return _handoff([vid], langs, token, 1, max_charge_usd, local={vid: result})[0]


def get_transcripts(inputs: Iterable[str], languages: Iterable[str] = ("en",), *,
                    apify: bool = False, apify_token: Optional[str] = None,
                    max_videos: int = _apify.DEFAULT_MAX_VIDEOS,
                    max_charge_usd: float = _apify.DEFAULT_MAX_CHARGE_USD,
                    http_client=None) -> List[TranscriptResult]:
    """
    Many videos, channels and playlists. Videos are tried locally first (free).
    With `apify=True` and a token, the ones YouTube refused, plus every channel
    and playlist, go to the actor in ONE run, capped at `max_charge_usd`.
    Without it, channels and playlists come back as ERROR with a hint.
    """
    langs = list(languages) or ["en"]
    results: List[TranscriptResult] = []
    local, collections = {}, []
    for item in inputs:
        item = item.strip()
        if not item:
            continue
        if is_collection(item):
            collections.append(item)
            continue
        try:
            vid = parse_video_id(item)
        except ValueError as e:
            results.append(TranscriptResult(status=ERROR, detail=str(e), input=item))
            continue
        r = fetch_local(vid, langs, http_client=http_client)
        if vid != item:
            r.input = item
        local[vid] = r
    token = apify_token or _apify.token_from_env()
    retry = [v for v, r in local.items() if r.status in HANDOFF]
    if apify and token and (retry or collections):
        handed = _handoff(retry + collections, langs, token, max_videos, max_charge_usd,
                          local={v: local[v] for v in retry})
        by_vid = {r.video_id: r for r in handed if r.video_id in local}
        results += [by_vid.get(v, r) for v, r in local.items()]
        results += [r for r in handed if r.video_id not in local]
        return results
    results += [_hint(r) for r in local.values()]
    for c in collections:
        results.append(TranscriptResult(status=ERROR, input=c,
                                        detail="a channel or playlist needs the Apify handoff",
                                        hint=HINT_COLLECTION))
    return results


def _handoff(items, langs, token, max_videos, max_charge_usd, local) -> List[TranscriptResult]:
    """One actor run. On any failure to run it, the local results stand, with why."""
    try:
        out = _apify.run(items, langs, token=token, max_videos=max_videos,
                         max_charge_usd=max_charge_usd)
    except Exception as e:                         # noqa: BLE001
        kept = list(local.values())
        for r in kept:
            r.detail = f"{r.detail}; Apify handoff failed: {e}"
        return kept
    results = _apify.fill_missing(list(local), out["results"], out["run_status"],
                                  out["status_message"])
    for r in results:
        if r.video_id in local:
            r.detail = (f"local: {local[r.video_id].status}; " + r.detail).rstrip("; ")
    return results
