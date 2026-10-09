"""
Fetch one YouTube transcript and say honestly what happened.

The fetching is done by youtube-transcript-api (MIT, Jonas Depoix). This module
adds one thing on top: a status you can trust. Above all, a request YouTube
refused is never reported as "this video has no captions".

Why that needs code of its own: when YouTube refuses a request it often answers
with a player response that simply has no captions block. youtube-transcript-api
reads that as `TranscriptsDisabled`, so a blocked server and a video without
subtitles raise the same exception. Here, NO_CAPTIONS is returned from exactly
one place, and only after checking that YouTube actually served the video it was
asked about (see `player_refusal`).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    FailedToCreateConsentCookie,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
    YouTubeTranscriptApi,
)

# ── statuses ──────────────────────────────────────────────────────────────────
OK = "OK"
NO_CAPTIONS = "NO_CAPTIONS"                    # YouTube served the video; it has no subtitles
BLOCKED = "BLOCKED"                            # YouTube refused this machine (bot check, captcha, 403…)
RATE_LIMITED = "RATE_LIMITED"                  # HTTP 429: too many requests from this IP
AGE_RESTRICTED = "AGE_RESTRICTED"              # needs a signed-in, age-verified account
PRIVATE = "PRIVATE"                            # private or members-only
REMOVED = "REMOVED"                            # deleted, terminated, or never existed
LANGUAGE_UNAVAILABLE = "LANGUAGE_UNAVAILABLE"  # captions exist, none in the languages asked for
ERROR = "ERROR"                                # anything we cannot classify honestly (network down, a YouTube change)

STATUSES = (OK, NO_CAPTIONS, BLOCKED, RATE_LIMITED, AGE_RESTRICTED, PRIVATE,
            REMOVED, LANGUAGE_UNAVAILABLE, ERROR)
# Worth asking again later or from elsewhere. The rest are facts about the video.
RETRYABLE = (BLOCKED, RATE_LIMITED, ERROR)

HINT_NO_TOKEN = ("YouTube refused this machine. Retry from a home connection, or set "
                 "APIFY_TOKEN and use --apify to fetch through the aquixlabs Apify actor "
                 "(paid per transcript; see README).")
HINT_WITH_TOKEN = ("YouTube refused this machine. APIFY_TOKEN is set: add --apify (Python: "
                   "apify=True) to retry through the aquixlabs Apify actor, paid per transcript.")


@dataclass
class TranscriptResult:
    status: str
    video_id: Optional[str] = None
    detail: str = ""
    language: Optional[str] = None             # e.g. "English (auto-generated)"
    language_code: Optional[str] = None        # e.g. "en"
    is_generated: Optional[bool] = None
    text: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None   # [{"start": s, "duration": s, "text": …}]
    available_languages: Optional[List[str]] = None   # set on LANGUAGE_UNAVAILABLE
    source: str = "local"                      # "local" or "apify"
    hint: Optional[str] = None
    input: Optional[str] = None                # what the caller passed, when it was not a bare ID

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["retryable"] = self.retryable
        return d


# ── input ─────────────────────────────────────────────────────────────────────
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PATH_ID = re.compile(r"^/(?:shorts|embed|live|v|e)/([A-Za-z0-9_-]{11})(?:[/?#]|$)")
_YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
             "youtube-nocookie.com", "www.youtube-nocookie.com")


def _url(s: str):
    return urlparse(s if "://" in s else "https://" + s)


def parse_video_id(video: str) -> str:
    """An 11-character video ID from an ID or any common YouTube video URL.
    Raises ValueError for anything else, including channels and playlists."""
    s = (video or "").strip()
    if _ID.match(s):
        return s
    if is_collection(s):
        raise ValueError(f"{s!r} is a channel or playlist, not a video. "
                         "Use get_transcripts(..., apify=True) / the CLI with --apify.")
    u = _url(s)
    host = (u.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        vid = u.path.strip("/").split("/")[0]
        if _ID.match(vid):
            return vid
    if host in _YT_HOSTS:
        vid = (parse_qs(u.query).get("v") or [""])[0]
        if _ID.match(vid):
            return vid
        m = _PATH_ID.match(u.path)
        if m:
            return m.group(1)
    raise ValueError(f"not a YouTube video ID or URL: {s!r}")


def is_collection(s: str) -> bool:
    """True for a channel (@handle, /channel/UC…, /c/…, /user/…) or a playlist
    URL without a video in it. A watch URL that carries a playlist is a video."""
    s = (s or "").strip()
    if s.startswith("@") and len(s) > 1 and "/" not in s:
        return True
    if "://" not in s and not s.lower().startswith(_YT_HOSTS):
        return False
    u = _url(s)
    if (u.hostname or "").lower() not in _YT_HOSTS:
        return False
    q = parse_qs(u.query)
    if q.get("v"):
        return False
    path = u.path
    return (path.startswith(("/@", "/channel/", "/c/", "/user/"))
            or (path.startswith("/playlist") and bool(q.get("list"))))


# ── classification ────────────────────────────────────────────────────────────
class _Watcher:
    """Remembers what YouTube actually answered, so a failure can be judged on
    the evidence rather than on which exception the library happened to raise."""

    PLAYER_PATH = "/youtubei/v1/player"

    def __init__(self):
        self.statuses: List[int] = []
        self.player: Optional[dict] = None

    def hook(self, response, *args, **kwargs):
        self.statuses.append(response.status_code)
        if self.PLAYER_PATH in (response.url or "") and response.status_code == 200:
            try:
                self.player = response.json()
            except ValueError:
                self.player = None
        return response


def _tracks(player: Optional[dict]) -> List[dict]:
    caps = ((player or {}).get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}
    return [t for t in caps.get("captionTracks") or [] if isinstance(t, dict)]


def player_refusal(player: Optional[dict], video_id: str) -> Optional[str]:
    """
    Why this player response is NOT a real answer about subtitles, or None if
    it is one. Ported from the aquixlabs actor, where it was measured: 3 of 59
    "no captions" answers were refusals that returned full transcripts on a
    re-fetch.

    A real answer: playabilityStatus OK, videoDetails for the video we asked
    about, and, if any caption tracks are listed, at least one with a URL.
    """
    if not isinstance(player, dict):
        return "no player response was read"
    ps = player.get("playabilityStatus") or {}
    if ps.get("status") != "OK":
        return f"playabilityStatus {ps.get('status')!r}: {ps.get('reason') or 'no reason given'}"
    if (player.get("videoDetails") or {}).get("videoId") != video_id:
        return "playabilityStatus OK but no videoDetails for this video (a degraded response)"
    listed = _tracks(player)
    if listed and not any(t.get("baseUrl") for t in listed):
        return f"{len(listed)} caption track(s) listed with their URLs withheld"
    return None


# Reason text → status, for a video YouTube will not play. Order matters: a
# geo block says "Video unavailable" too, but it is about where you are.
_REASONS = (
    (BLOCKED, ("not a bot", "in your country", "not made this video available")),
    (AGE_RESTRICTED, ("confirm your age", "inappropriate for some users",
                      "age-restricted", "age restricted")),
    (PRIVATE, ("video is private", "members-only", "members only", "join this channel")),
    (REMOVED, ("video unavailable", "video is unavailable", "no longer available",
               "has been removed", "has been terminated")),
)


def status_for_reason(reason: Optional[str]) -> Optional[str]:
    r = (reason or "").lower()
    for status, needles in _REASONS:
        if any(n in r for n in needles):
            return status
    return None


def classify(exc: BaseException, video_id: str, player: Optional[dict],
             statuses: Iterable[int]) -> TranscriptResult:
    """Turn a failure into one honest status. Pure: no network."""
    def res(status, detail, **kw):
        return TranscriptResult(status=status, video_id=video_id, detail=detail, **kw)

    if 429 in list(statuses):
        return res(RATE_LIMITED, "YouTube answered HTTP 429 (too many requests from this IP)")
    if isinstance(exc, AgeRestricted):
        return res(AGE_RESTRICTED, "YouTube requires a signed-in, age-verified account")
    if isinstance(exc, VideoUnavailable):
        return res(REMOVED, "YouTube says the video is unavailable (removed, or the ID never existed)")
    if isinstance(exc, IpBlocked):
        return res(BLOCKED, "YouTube served a captcha page instead of the video")
    if isinstance(exc, RequestBlocked):
        return res(BLOCKED, "YouTube asked this machine to sign in to prove it is not a bot")
    if isinstance(exc, PoTokenRequired):
        return res(BLOCKED, "YouTube demands a proof-of-origin token for this caption track")
    if isinstance(exc, VideoUnplayable):
        reason = " ".join(filter(None, [exc.reason] + list(exc.sub_reasons or [])))
        status = status_for_reason(reason)
        if status:
            return res(status, f"YouTube: {reason}")
        return res(ERROR, f"YouTube will not play the video, for a reason this version does "
                          f"not recognise: {reason or 'none given'}")
    if isinstance(exc, NoTranscriptFound):
        langs = sorted({t.get("languageCode") for t in _tracks(player) if t.get("languageCode")})
        return res(LANGUAGE_UNAVAILABLE, "captions exist, but not in the languages asked for",
                   available_languages=langs or None)

    # Everything below may be a refusal dressed up as something else. Judge the
    # player response itself before believing the exception.
    refusal = player_refusal(player, video_id)
    if isinstance(exc, TranscriptsDisabled):
        if refusal is None and not _tracks(player):
            # ★ The only line in this package that returns NO_CAPTIONS.
            return res(NO_CAPTIONS, "YouTube served the video and it lists no caption tracks")
        return res(BLOCKED, f"no captions in the response, but it was not a real answer: "
                            f"{refusal or 'tracks were listed'}")
    if refusal is not None and player is not None:
        return res(BLOCKED, refusal)
    if isinstance(exc, YouTubeRequestFailed):
        if " 403 " in f" {exc.reason} " or "403 Client Error" in exc.reason:
            return res(BLOCKED, f"YouTube refused the request: {exc.reason}")
        return res(ERROR, f"request to YouTube failed: {exc.reason}")
    if isinstance(exc, (YouTubeDataUnparsable, FailedToCreateConsentCookie)):
        return res(ERROR, "YouTube returned a page this version cannot read (an interstitial, "
                          "a consent page, or a YouTube change)")
    if isinstance(exc, InvalidVideoId):
        return res(ERROR, "not a valid video ID")
    if isinstance(exc, requests.RequestException):
        return res(ERROR, f"could not reach YouTube: {exc.__class__.__name__}: {exc}")
    if player is not None and _tracks(player):
        # YouTube served the video and listed tracks, yet reading one failed
        # (an empty body is the usual shape of a refused track request).
        return res(BLOCKED, f"a caption track was listed but could not be read "
                            f"({exc.__class__.__name__})")
    if isinstance(exc, CouldNotRetrieveTranscript):
        return res(ERROR, f"{exc.__class__.__name__}")
    return res(ERROR, f"unexpected {exc.__class__.__name__}: {exc}")


# ── fetching ──────────────────────────────────────────────────────────────────
def fetch_local(video_id: str, languages: Iterable[str] = ("en",),
                http_client: Optional[requests.Session] = None) -> TranscriptResult:
    """One video, from this machine, through youtube-transcript-api. Never raises."""
    langs = list(languages) or ["en"]
    session = http_client if http_client is not None else requests.Session()
    watcher = _Watcher()
    session.hooks.setdefault("response", []).append(watcher.hook)
    try:
        api = YouTubeTranscriptApi(http_client=session)
        transcript = api.list(video_id).find_transcript(langs)
        fetched = transcript.fetch()
    except Exception as exc:                       # noqa: BLE001 — classified, never raised
        return classify(exc, video_id, watcher.player, watcher.statuses)
    finally:
        try:
            session.hooks["response"].remove(watcher.hook)
        except ValueError:
            pass
    segments = [{"start": s.start, "duration": s.duration, "text": s.text}
                for s in fetched.snippets if s.text.strip()]
    if not segments:
        return TranscriptResult(
            status=BLOCKED, video_id=video_id, language=fetched.language,
            language_code=fetched.language_code, is_generated=fetched.is_generated,
            detail="the caption track came back empty, which is usually how YouTube "
                   "refuses a track request")
    return TranscriptResult(
        status=OK, video_id=video_id, language=fetched.language,
        language_code=fetched.language_code, is_generated=fetched.is_generated,
        text=" ".join(s["text"] for s in segments), segments=segments)
