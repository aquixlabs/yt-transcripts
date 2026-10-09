"""
MCP server: `yt-transcripts-mcp` (stdio).

Tools
  get_transcript   one video, local and free; long transcripts are paged
  get_transcripts  several videos, channels or playlists; channels/playlists
                   and refused videos need use_apify=True (paid, user's token)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import get_transcript as _get_transcript
from . import get_transcripts as _get_transcripts
from .apify import DEFAULT_MAX_CHARGE_USD, DEFAULT_MAX_VIDEOS

try:                                    # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                     # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

DEFAULT_MAX_CHARS = 40_000

INSTRUCTIONS = (
    "Every result has a `status`. Only OK carries text. NO_CAPTIONS means the video "
    "truly has no captions. BLOCKED / RATE_LIMITED mean YouTube refused this machine: "
    "do not tell the user the video has no captions. use_apify=True retries through a "
    "PAID Apify actor on the user's own APIFY_TOKEN; ask the user before using it.")

server = _Server("yt-transcripts", instructions=INSTRUCTIONS)


def page(d: Dict[str, Any], offset: int, max_chars: int, segments: bool) -> Dict[str, Any]:
    """Cut the text to one page so a 3-hour video does not flood the context."""
    text = d.get("text")
    if not segments:
        d.pop("segments", None)
    if text is None:
        return d
    max_chars = max(1000, int(max_chars))
    offset = max(0, int(offset))
    chunk = text[offset:offset + max_chars]
    d["text"] = chunk
    d["total_chars"] = len(text)
    d["offset"] = offset
    d["next_offset"] = offset + len(chunk) if offset + len(chunk) < len(text) else None
    return d


@server.tool()
def get_transcript(video: str, languages: Optional[List[str]] = None, offset: int = 0,
                   max_chars: int = DEFAULT_MAX_CHARS, include_segments: bool = False,
                   use_apify: bool = False) -> Dict[str, Any]:
    """Transcript of one YouTube video (ID or URL) with an honest status.
    Long transcripts are paged: call again with offset=next_offset.
    include_segments adds timed segments. use_apify=True is PAID (user's APIFY_TOKEN):
    only after the user agrees, and only if status was BLOCKED or RATE_LIMITED."""
    try:
        r = _get_transcript(video, languages or ["en"], apify=use_apify)
    except ValueError as e:
        return {"status": "ERROR", "detail": str(e), "retryable": False}
    return page(r.to_dict(), offset, max_chars, include_segments)


@server.tool()
def get_transcripts(inputs: List[str], languages: Optional[List[str]] = None,
                    use_apify: bool = False, max_videos: int = DEFAULT_MAX_VIDEOS,
                    max_charge_usd: float = DEFAULT_MAX_CHARGE_USD,
                    max_chars_each: int = 8_000) -> List[Dict[str, Any]]:
    """Transcripts for several videos, channels (@handle) or playlists.
    Channels/playlists need use_apify=True: PAID per transcript on the user's own
    APIFY_TOKEN, capped at max_charge_usd. Ask the user before using it.
    Each text is cut to max_chars_each; fetch one video with get_transcript to page it."""
    rs = _get_transcripts(inputs, languages or ["en"], apify=use_apify,
                          max_videos=max_videos, max_charge_usd=max_charge_usd)
    return [page(r.to_dict(), 0, max_chars_each, False) for r in rs]


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
