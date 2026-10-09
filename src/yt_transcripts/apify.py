"""
Optional handoff to the aquixlabs Apify actor, for when YouTube blocks this
machine or you want a whole channel or playlist.

★ DISCLOSURE: aquixlabs/youtube-channel-scraper is OUR actor, and it is paid per
transcript. It runs on YOUR Apify account with YOUR token (the APIFY_TOKEN
environment variable), so the charges are yours. Nothing here runs unless the
caller asks for it explicitly (apify=True / --apify); a token sitting in the
environment is not consent.

Every run is started with a spend cap (`maxTotalChargeUsd`), which the actor
honours: it stops before the cap and does not charge for what it skipped.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, List, Optional

import requests

from .core import (AGE_RESTRICTED, BLOCKED, ERROR, LANGUAGE_UNAVAILABLE, NO_CAPTIONS, OK,
                   PRIVATE, REMOVED, TranscriptResult)

ACTOR_SLUG = "aquixlabs/youtube-channel-scraper"
ACTOR_ID = "WS0JZ8maNpYn3lGRV"      # addressed by ID: a rename would break the slug, not this
API = "https://api.apify.com/v2"
DEFAULT_MAX_CHARGE_USD = 0.50
DEFAULT_MAX_VIDEOS = 20
TIMEOUT_S = 600
TERMINAL = ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT")


class ApifyError(RuntimeError):
    pass


def token_from_env() -> Optional[str]:
    return os.environ.get("APIFY_TOKEN") or None


def build_input(inputs: Iterable[str], languages: Iterable[str], max_videos: int) -> Dict[str, Any]:
    """The actor input. Strict language matching, so the actor answers like the
    local path does (LANGUAGE_UNAVAILABLE rather than another language's text)."""
    return {
        "inputs": list(inputs),
        "includeTranscript": True,
        "includeTranscriptSegments": True,
        "transcriptLanguages": list(languages) or ["en"],
        "strictTranscriptLanguage": True,
        "maxResultsPerSource": int(max_videos),
        "maxItems": int(max_videos),
        "includeComments": False,
        "includeLikes": False,
    }


# The actor's transcript_status values → ours.
_STATUS = {
    "OK": OK,
    "NO_CAPTIONS": NO_CAPTIONS,
    "EMPTY_TRACK": NO_CAPTIONS,
    "NO_REQUESTED_LANGUAGE": LANGUAGE_UNAVAILABLE,
    "UNAVAILABLE: AGE_RESTRICTED": AGE_RESTRICTED,
    "UNAVAILABLE: PRIVATE": PRIVATE,
    "UNAVAILABLE: MEMBERS_ONLY": PRIVATE,
    "UNAVAILABLE: REMOVED": REMOVED,
}
_NO_DATA_PREFIX = (("REMOVED", REMOVED), ("PRIVATE", PRIVATE),
                   ("AGE_RESTRICTED", AGE_RESTRICTED), ("MEMBERS_ONLY", PRIVATE))


def row_to_result(row: Dict[str, Any]) -> TranscriptResult:
    """One actor dataset row → one result. Pure: no network."""
    vid = row.get("video_id")
    base = dict(video_id=vid, source="apify", input=row.get("_input"))
    if row.get("_error"):
        err = str(row["_error"])
        if row.get("_error_kind") == "NO_DATA":
            for prefix, status in _NO_DATA_PREFIX:
                if err.upper().startswith(prefix):
                    return TranscriptResult(status=status, detail=f"actor: {err}", **base)
        return TranscriptResult(status=ERROR, detail=f"actor {row.get('_error_kind') or 'error'}: {err}",
                                **base)
    raw = row.get("transcript_status")
    if raw is None:
        return TranscriptResult(status=ERROR, detail="actor returned no transcript status", **base)
    status = _STATUS.get(raw)
    if status is None:
        if raw.startswith(("UNAVAILABLE:", "TRACK_FETCH_FAILED")):
            status = BLOCKED
        else:
            return TranscriptResult(status=ERROR, detail=f"actor status not recognised: {raw}", **base)
    lang = row.get("transcript_language")
    result = TranscriptResult(status=status, detail=f"actor: {raw}", language_code=lang,
                              is_generated=row.get("transcript_is_generated"), **base)
    if status == OK:
        segs = [{"start": s.get("start_s"), "duration": s.get("duration_s"), "text": s.get("text")}
                for s in row.get("transcript_segments") or [] if isinstance(s, dict)]
        result.segments = segs or None
        result.text = row.get("transcript")
        result.detail = ""
        if not result.text:
            result.status, result.detail = ERROR, "actor said OK but returned no text"
    elif status == LANGUAGE_UNAVAILABLE and lang:
        result.available_languages = [lang]
    return result


def rows_to_results(rows: Iterable[Dict[str, Any]]) -> List[TranscriptResult]:
    """Video rows only; comment rows are never requested but are skipped if present."""
    return [row_to_result(r) for r in rows
            if isinstance(r, dict) and r.get("_row_type", "video") == "video"]


def run(inputs: List[str], languages: Iterable[str] = ("en",), token: Optional[str] = None,
        max_videos: int = DEFAULT_MAX_VIDEOS, max_charge_usd: float = DEFAULT_MAX_CHARGE_USD,
        timeout_s: int = TIMEOUT_S, session: Optional[requests.Session] = None,
        ) -> Dict[str, Any]:
    """
    Run the actor once on `inputs` (video IDs, channels, playlists) and return
    {"results": [...], "run_id": …, "run_status": …, "status_message": …}.
    Raises ApifyError only for problems before the run exists (no token, bad
    token, actor not reachable). If the run outlives `timeout_s` it is aborted,
    so it stops spending.
    """
    token = token or token_from_env()
    if not token:
        raise ApifyError("APIFY_TOKEN is not set")
    http = session or requests.Session()
    auth = {"Authorization": f"Bearer {token}"}
    r = http.post(f"{API}/acts/{ACTOR_ID}/runs", headers=auth,
                  params={"maxTotalChargeUsd": f"{float(max_charge_usd):.2f}", "waitForFinish": 60},
                  json=build_input(inputs, languages, max_videos), timeout=90)
    if r.status_code >= 400:
        raise ApifyError(f"could not start the actor: HTTP {r.status_code} {r.text[:200]}")
    data = r.json().get("data") or {}
    run_id = data.get("id")
    deadline = time.monotonic() + timeout_s
    while data.get("status") not in TERMINAL:
        if time.monotonic() > deadline:
            http.post(f"{API}/actor-runs/{run_id}/abort", headers=auth, timeout=30)
            data["status"] = "ABORTED"
            data["statusMessage"] = f"aborted by yt-transcripts after {timeout_s}s"
            break
        r = http.get(f"{API}/actor-runs/{run_id}", headers=auth,
                     params={"waitForFinish": 60}, timeout=90)
        if r.status_code >= 400:
            raise ApifyError(f"could not read run {run_id}: HTTP {r.status_code}")
        data = r.json().get("data") or {}
    rows: List[Dict[str, Any]] = []
    if data.get("defaultDatasetId"):
        r = http.get(f"{API}/datasets/{data['defaultDatasetId']}/items", headers=auth,
                     params={"format": "json", "clean": "false"}, timeout=120)
        if r.status_code < 400:
            rows = r.json()
    return {"results": rows_to_results(rows), "run_id": run_id,
            "run_status": data.get("status"), "status_message": data.get("statusMessage")}


def fill_missing(video_ids: Iterable[str], results: List[TranscriptResult],
                 run_status: Optional[str], status_message: Optional[str]) -> List[TranscriptResult]:
    """Add an ERROR result for each requested video the run did not return
    (e.g. skipped at the spend cap), so nothing silently disappears."""
    seen = {r.video_id for r in results}
    why = status_message or f"run ended {run_status or 'without a status'}"
    return results + [TranscriptResult(status=ERROR, video_id=v, source="apify",
                                       detail=f"not returned by the actor run: {why}")
                      for v in video_ids if v not in seen]
