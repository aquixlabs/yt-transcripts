"""
The Apify handoff, offline: the actor's row → our status, and the run protocol
against a fake HTTP session. No request ever reaches Apify.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_transcripts as yt  # noqa: E402
from yt_transcripts import apify  # noqa: E402

VID = "dQw4w9WgXcQ"


def row(**kw):
    base = {"_row_type": "video", "video_id": VID, "_input": VID}
    base.update(kw)
    return base


class RowMapping(unittest.TestCase):
    def test_ok(self):
        r = apify.row_to_result(row(transcript_status="OK", transcript="hello world",
                                    transcript_language="en", transcript_is_generated=True,
                                    transcript_segments=[{"start_s": 0.0, "duration_s": 1.5,
                                                          "text": "hello world"}]))
        self.assertEqual((r.status, r.source, r.text, r.language_code, r.is_generated),
                         (yt.OK, "apify", "hello world", "en", True))
        self.assertEqual(r.segments, [{"start": 0.0, "duration": 1.5, "text": "hello world"}])

    def test_each_actor_status(self):
        cases = {
            "NO_CAPTIONS": yt.NO_CAPTIONS,
            "EMPTY_TRACK": yt.NO_CAPTIONS,
            "NO_REQUESTED_LANGUAGE": yt.LANGUAGE_UNAVAILABLE,
            "UNAVAILABLE: AGE_RESTRICTED": yt.AGE_RESTRICTED,
            "UNAVAILABLE: PRIVATE": yt.PRIVATE,
            "UNAVAILABLE: MEMBERS_ONLY": yt.PRIVATE,
            "UNAVAILABLE: REMOVED": yt.REMOVED,
            "UNAVAILABLE: bot check after 3 attempts": yt.BLOCKED,
            "TRACK_FETCH_FAILED: HTTP 403": yt.BLOCKED,
            "SOMETHING_NEW": yt.ERROR,
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(apify.row_to_result(row(transcript_status=raw)).status, want)

    def test_ok_without_text_is_error(self):
        self.assertEqual(apify.row_to_result(row(transcript_status="OK", transcript="")).status,
                         yt.ERROR)

    def test_missing_status_is_error(self):
        self.assertEqual(apify.row_to_result(row()).status, yt.ERROR)

    def test_error_rows(self):
        r = apify.row_to_result(row(_error="REMOVED: Video unavailable", _error_kind="NO_DATA"))
        self.assertEqual(r.status, yt.REMOVED)
        r = apify.row_to_result(row(_error="HTTP 500", _error_kind="FETCH_FAILED"))
        self.assertEqual(r.status, yt.ERROR)

    def test_comment_rows_skipped(self):
        rs = apify.rows_to_results([row(transcript_status="NO_CAPTIONS"),
                                    {"_row_type": "comment", "video_id": VID}])
        self.assertEqual(len(rs), 1)

    def test_fill_missing_never_drops_a_video(self):
        rs = apify.fill_missing(["a" * 11, "b" * 11],
                                [yt.TranscriptResult(status=yt.OK, video_id="a" * 11)],
                                "SUCCEEDED", "Stopped at your spend cap: 1 video not fetched")
        self.assertEqual([r.status for r in rs], [yt.OK, yt.ERROR])
        self.assertIn("spend cap", rs[1].detail)

    def test_input_is_strict_and_capped(self):
        i = apify.build_input(["@x"], ["de", "en"], 7)
        self.assertEqual((i["strictTranscriptLanguage"], i["maxItems"], i["maxResultsPerSource"],
                          i["transcriptLanguages"], i["includeTranscript"]),
                         (True, 7, 7, ["de", "en"], True))


class Resp:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, str(data)

    def json(self):
        return self._data


class FakeApify:
    """Records every call. Never touches the network."""

    def __init__(self, statuses=("RUNNING", "SUCCEEDED"), items=()):
        self.statuses = list(statuses)
        self.items = list(items)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        if url.endswith("/abort"):
            return Resp(200, {"data": {"status": "ABORTED"}})
        return Resp(201, {"data": {"id": "run1", "status": self.statuses.pop(0),
                                   "defaultDatasetId": "ds1"}})

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        if "/datasets/" in url:
            return Resp(200, self.items)
        st = self.statuses.pop(0) if self.statuses else "RUNNING"
        return Resp(200, {"data": {"id": "run1", "status": st, "defaultDatasetId": "ds1"}})


class RunProtocol(unittest.TestCase):
    def test_run_uses_actor_id_token_and_spend_cap(self):
        http = FakeApify(items=[row(transcript_status="OK", transcript="hi")])
        out = apify.run([VID], ["en"], token="test-token-not-real", max_charge_usd=0.25,
                        session=http)
        method, url, kw = http.calls[0]
        self.assertEqual(method, "POST")
        self.assertIn(f"/acts/{apify.ACTOR_ID}/runs", url)
        self.assertEqual(kw["params"]["maxTotalChargeUsd"], "0.25")
        self.assertEqual(kw["headers"]["Authorization"], "Bearer test-token-not-real")
        self.assertNotIn("token", url)                 # never in a URL, where logs keep it
        self.assertEqual((out["run_status"], out["results"][0].status), ("SUCCEEDED", yt.OK))

    def test_timeout_aborts_the_run(self):
        http = FakeApify(statuses=["RUNNING"])
        with mock.patch.object(apify.time, "monotonic", side_effect=[0, 0, 10_000]):
            out = apify.run([VID], token="test-token-not-real", timeout_s=5, session=http)
        self.assertTrue(any(u.endswith("/actor-runs/run1/abort") for _, u, _ in http.calls))
        self.assertEqual(out["run_status"], "ABORTED")

    def test_no_token_raises_before_any_call(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(apify.ApifyError):
                apify.run([VID], session=FakeApify())


if __name__ == "__main__":
    unittest.main()
