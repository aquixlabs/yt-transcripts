"""
Rebuild tests/fixtures from youtube-transcript-api's own recorded responses
(installed with the package, MIT) plus a few synthesized cases. No network.

    python tools/build_fixtures.py

RECORDED files are real YouTube responses captured by the upstream project,
trimmed to the three keys the classifier reads. SYNTHESIZED files are built
from a recorded one with one field changed; each says what and why in
SOURCES.md. Only the INNERTUBE key in watch.html is a placeholder.
"""
import copy
import json
import os
import shutil

import youtube_transcript_api

UP = os.path.join(os.path.dirname(youtube_transcript_api.__file__), "test", "assets")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "tests", "fixtures")
KEEP = ("playabilityStatus", "videoDetails", "captions")


def load(name):
    with open(os.path.join(UP, name), encoding="utf-8") as f:
        return json.load(f)


def trim(d):
    out = {k: d[k] for k in KEEP if k in d}
    if "videoDetails" in out:
        out["videoDetails"] = {k: out["videoDetails"][k]
                               for k in ("videoId", "title") if k in out["videoDetails"]}
    if "playabilityStatus" in out:     # drop the large rendered error screens' images
        ps = out["playabilityStatus"]
        out["playabilityStatus"] = {k: ps[k] for k in ("status", "reason", "errorScreen")
                                    if k in ps}
    return out


def save(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    recorded = {
        "player_ok.json": "youtube.innertube.json.static",
        "player_no_captions.json": "youtube_transcripts_disabled.innertube.json.static",
        "player_no_captions2.json": "youtube_transcripts_disabled2.innertube.json.static",
        "player_age_restricted.json": "youtube_age_restricted.innertube.json.static",
        "player_bot_check.json": "youtube_request_blocked.innertube.json.static",
        "player_unavailable.json": "youtube_video_unavailable.innertube.json.static",
        "player_unplayable_custom.json": "youtube_unplayable.innertube.json.static",
        "player_po_token.json": "youtube_po_token_required.innertube.json.static",
    }
    for out, src in recorded.items():
        save(out, trim(load(src)))
    shutil.copy(os.path.join(UP, "youtube_too_many_requests.html.static"),
                os.path.join(OUT, "watch_captcha.html"))
    shutil.copy(os.path.join(UP, "transcript.xml.static"), os.path.join(OUT, "transcript.xml"))

    # SYNTHESIZED ---------------------------------------------------------
    ok = trim(load("youtube.innertube.json.static"))
    unplayable = trim(load("youtube_unplayable.innertube.json.static"))

    private = copy.deepcopy(unplayable)
    private["playabilityStatus"] = {"status": "LOGIN_REQUIRED", "reason": "This video is private"}
    save("player_private.json", private)

    members = copy.deepcopy(unplayable)
    members["playabilityStatus"] = {
        "status": "UNPLAYABLE",
        "reason": "Join this channel to get access to members-only content like this video, and more."}
    save("player_members_only.json", members)

    geo = copy.deepcopy(unplayable)
    geo["playabilityStatus"] = {
        "status": "UNPLAYABLE", "reason": "Video unavailable",
        "errorScreen": {"playerErrorMessageRenderer": {"subreason": {"runs": [
            {"text": "The uploader has not made this video available in your country"}]}}}}
    save("player_geo_blocked.json", geo)

    degraded = {"playabilityStatus": {"status": "OK"}}
    save("player_degraded.json", degraded)

    other_video = copy.deepcopy(trim(load("youtube_transcripts_disabled.innertube.json.static")))
    other_video["videoDetails"]["videoId"] = "AAAAAAAAAAA"
    save("player_wrong_video.json", other_video)

    no_url = copy.deepcopy(ok)
    for t in no_url["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]:
        t.pop("baseUrl", None)
    save("player_tracks_no_url.json", no_url)

    with open(os.path.join(OUT, "watch.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><html><head><script>ytcfg.set({"INNERTUBE_API_KEY": '
                '"FIXTURE_PLACEHOLDER_KEY"});</script></head><body></body></html>\n')
    with open(os.path.join(OUT, "transcript_empty.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8" ?>\n<transcript></transcript>\n')
    print("fixtures written to", OUT)


if __name__ == "__main__":
    main()
