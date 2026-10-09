"""
Every status, classified from recorded YouTube responses. No network.

    python -m unittest discover -s tests
"""
import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakeyt import session  # noqa: E402

import yt_transcripts as yt  # noqa: E402
from yt_transcripts import apify as yt_apify  # noqa: E402
from yt_transcripts.core import fetch_local  # noqa: E402

OK_ID = "GJLlxj_dtq8"           # the recorded fixtures' own video IDs
NOCAP_ID = "dsMFmonKDD4"
NOCAP2_ID = "Fjg5lYqvzUs"
ANY_ID = "Njp5uhTorCo"


def run(video_id, langs=("en",), **routes):
    return fetch_local(video_id, langs, http_client=session(**routes))


class Statuses(unittest.TestCase):
    # OK ------------------------------------------------------------------
    def test_ok(self):
        r = run(OK_ID, player=(200, "player_ok.json"))
        self.assertEqual(r.status, yt.OK, r.detail)
        self.assertEqual(r.language_code, "en")
        self.assertFalse(r.is_generated)
        self.assertEqual(r.text, "Hey, this is just a test this is not the original transcript "
                                 "just something shorter, I made up for testing")
        self.assertEqual(r.segments[0], {"start": 0.0, "duration": 1.54,
                                         "text": "Hey, this is just a test"})
        self.assertEqual(len(r.segments), 3)          # the empty cue is dropped

    def test_language_preference_order(self):
        r = run(OK_ID, langs=("de", "en"), player=(200, "player_ok.json"))
        self.assertEqual((r.status, r.language_code), (yt.OK, "de"))

    # NO_CAPTIONS: only when YouTube really served the video ---------------
    def test_no_captions(self):
        r = run(NOCAP_ID, player=(200, "player_no_captions.json"))
        self.assertEqual(r.status, yt.NO_CAPTIONS, r.detail)

    def test_no_captions_second_recording(self):
        r = run(NOCAP2_ID, player=(200, "player_no_captions2.json"))
        self.assertEqual(r.status, yt.NO_CAPTIONS, r.detail)

    # BLOCKED: every refusal shape, none of them may say NO_CAPTIONS --------
    def test_bot_check(self):
        r = run(ANY_ID, player=(200, "player_bot_check.json"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_captcha_page(self):
        r = run(ANY_ID, watch=(200, "watch_captcha.html"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_degraded_response_is_not_no_captions(self):
        r = run(NOCAP_ID, player=(200, "player_degraded.json"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_response_for_another_video_is_not_no_captions(self):
        r = run(NOCAP_ID, player=(200, "player_wrong_video.json"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_tracks_with_urls_withheld(self):
        r = run(OK_ID, player=(200, "player_tracks_no_url.json"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_po_token_required(self):
        r = run(OK_ID, player=(200, "player_po_token.json"))   # the "en" track carries exp=xpe
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_geo_block_is_not_removed(self):
        r = run(ANY_ID, player=(200, "player_geo_blocked.json"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_http_403(self):
        r = run(OK_ID, player=(403, b"forbidden"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_empty_track(self):
        r = run(OK_ID, player=(200, "player_ok.json"), timedtext=(200, "transcript_empty.xml"))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    def test_zero_byte_track(self):
        r = run(OK_ID, player=(200, "player_ok.json"), timedtext=(200, b""))
        self.assertEqual(r.status, yt.BLOCKED, r.detail)

    # RATE_LIMITED ---------------------------------------------------------
    def test_429_on_watch_page(self):
        r = run(ANY_ID, watch=(429, b"too many"))
        self.assertEqual(r.status, yt.RATE_LIMITED, r.detail)

    def test_429_on_track(self):
        r = run(OK_ID, player=(200, "player_ok.json"), timedtext=(429, b""))
        self.assertEqual(r.status, yt.RATE_LIMITED, r.detail)

    # facts about the video ------------------------------------------------
    def test_age_restricted(self):
        r = run(ANY_ID, player=(200, "player_age_restricted.json"))
        self.assertEqual(r.status, yt.AGE_RESTRICTED, r.detail)

    def test_private(self):
        r = run(ANY_ID, player=(200, "player_private.json"))
        self.assertEqual(r.status, yt.PRIVATE, r.detail)

    def test_members_only(self):
        r = run(ANY_ID, player=(200, "player_members_only.json"))
        self.assertEqual(r.status, yt.PRIVATE, r.detail)

    def test_removed(self):
        r = run(ANY_ID, player=(200, "player_unavailable.json"))
        self.assertEqual(r.status, yt.REMOVED, r.detail)

    def test_language_unavailable(self):
        r = run(OK_ID, langs=("fr",), player=(200, "player_ok.json"))
        self.assertEqual(r.status, yt.LANGUAGE_UNAVAILABLE, r.detail)
        self.assertEqual(r.available_languages,
                         ["cs", "de", "en", "es", "hi", "ja", "ko", "zh"])

    # ERROR: honest "we don't know", never a guess -------------------------
    def test_unknown_unplayable_reason(self):
        r = run(ANY_ID, player=(200, "player_unplayable_custom.json"))
        self.assertEqual(r.status, yt.ERROR, r.detail)
        self.assertIn("Custom Reason", r.detail)

    def test_network_down(self):
        r = run(ANY_ID, watch=requests.ConnectionError("no route to host"))
        self.assertEqual(r.status, yt.ERROR, r.detail)

    def test_server_error(self):
        r = run(OK_ID, player=(500, b"oops"))
        self.assertEqual(r.status, yt.ERROR, r.detail)


class Invariants(unittest.TestCase):
    REFUSALS = [
        dict(player=(200, "player_bot_check.json")),
        dict(watch=(200, "watch_captcha.html")),
        dict(player=(200, "player_degraded.json")),
        dict(player=(200, "player_wrong_video.json")),
        dict(player=(200, "player_tracks_no_url.json")),
        dict(player=(403, b"")),
        dict(watch=(429, b"")),
        dict(player=(200, "player_geo_blocked.json")),
        dict(player=(500, b"")),
        dict(watch=requests.Timeout("slow")),
    ]

    def test_a_refusal_is_never_no_captions(self):
        for routes in self.REFUSALS:
            with self.subTest(routes=routes):
                r = run(NOCAP_ID, **routes)
                self.assertNotEqual(r.status, yt.NO_CAPTIONS, r.detail)
                self.assertTrue(r.retryable, r.status)

    def test_every_result_has_a_known_status(self):
        for routes in self.REFUSALS:
            self.assertIn(run(NOCAP_ID, **routes).status, yt.STATUSES)

    def test_facts_are_not_retryable(self):
        for st in (yt.OK, yt.NO_CAPTIONS, yt.AGE_RESTRICTED, yt.PRIVATE, yt.REMOVED,
                   yt.LANGUAGE_UNAVAILABLE):
            self.assertFalse(yt.TranscriptResult(status=st).retryable, st)


class Handoff(unittest.TestCase):
    """The paid path runs only when asked for AND a token exists. No real Apify calls."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("APIFY_TOKEN", None)
        self.actor = mock.patch.object(yt_apify, "run",
                                       side_effect=AssertionError("Apify must not be called"))
        self.actor.start()

    def tearDown(self):
        self.actor.stop()
        self.env.stop()

    def blocked(self, **kw):
        return yt.get_transcript(ANY_ID, http_client=session(player=(200, "player_bot_check.json")),
                                 **kw)

    def test_blocked_without_token_gives_hint_and_no_call(self):
        r = self.blocked(apify=True)
        self.assertEqual(r.status, yt.BLOCKED)
        self.assertIn("APIFY_TOKEN", r.hint)

    def test_token_alone_is_not_consent(self):
        os.environ["APIFY_TOKEN"] = "test-token-not-real"
        r = self.blocked()
        self.assertEqual(r.status, yt.BLOCKED)
        self.assertIn("--apify", r.hint)

    def test_handoff_when_asked_and_token_set(self):
        self.actor.stop()
        os.environ["APIFY_TOKEN"] = "test-token-not-real"
        fake = {"results": [yt.TranscriptResult(status=yt.OK, video_id=ANY_ID, text="hi",
                                                source="apify")],
                "run_id": "r1", "run_status": "SUCCEEDED", "status_message": None}
        with mock.patch.object(yt_apify, "run", return_value=fake) as called:
            r = self.blocked(apify=True, max_charge_usd=0.10)
        self.actor.start()
        self.assertEqual((r.status, r.source, r.text), (yt.OK, "apify", "hi"))
        self.assertIn("local: BLOCKED", r.detail)
        self.assertEqual(called.call_args.kwargs["max_charge_usd"], 0.10)

    def test_no_handoff_for_facts(self):
        os.environ["APIFY_TOKEN"] = "test-token-not-real"
        r = yt.get_transcript(NOCAP_ID, apify=True,
                              http_client=session(player=(200, "player_no_captions.json")))
        self.assertEqual(r.status, yt.NO_CAPTIONS)
        self.assertIsNone(r.hint)

    def test_channel_without_apify_is_error_with_hint(self):
        rs = yt.get_transcripts(["@somechannel"])
        self.assertEqual(rs[0].status, yt.ERROR)
        self.assertIn("APIFY_TOKEN", rs[0].hint)


class Inputs(unittest.TestCase):
    def test_video_forms(self):
        for s in ["dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                  "youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "https://youtu.be/dQw4w9WgXcQ?si=x",
                  "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
                  "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                  "https://www.youtube.com/embed/dQw4w9WgXcQ",
                  "https://www.youtube.com/live/dQw4w9WgXcQ?feature=share",
                  "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx"]:
            self.assertEqual(yt.parse_video_id(s), "dQw4w9WgXcQ", s)

    def test_collections(self):
        for s in ["@mkbhd", "https://www.youtube.com/@mkbhd", "https://www.youtube.com/@mkbhd/videos",
                  "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ",
                  "https://www.youtube.com/playlist?list=PL590L5WQmH8fJ54F369BLDSqIwcs-TCfs"]:
            self.assertTrue(yt.is_collection(s), s)
            with self.assertRaises(ValueError):
                yt.parse_video_id(s)

    def test_rejects(self):
        for s in ["", "hello", "https://vimeo.com/123456789", "dQw4w9WgXc", "https://youtu.be/"]:
            with self.assertRaises(ValueError):
                yt.parse_video_id(s)


if __name__ == "__main__":
    unittest.main()
