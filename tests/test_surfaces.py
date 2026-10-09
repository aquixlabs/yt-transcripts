"""CLI and MCP server: exit codes, output, paging, tool list. Offline."""
import asyncio
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yt_transcripts as yt  # noqa: E402
from yt_transcripts import cli  # noqa: E402

OK = yt.TranscriptResult(status=yt.OK, video_id="a" * 11, text="hello", language_code="en")
BLOCKED = yt.TranscriptResult(status=yt.BLOCKED, video_id="b" * 11, detail="bot check",
                              hint=yt.core.HINT_NO_TOKEN)


def run_cli(argv, results):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cli, "get_transcripts", return_value=results) as called, \
            redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue(), called


class Cli(unittest.TestCase):
    def test_ok_prints_text_and_exits_0(self):
        code, out, err, _ = run_cli(["a" * 11], [OK])
        self.assertEqual((code, out.strip()), (0, "hello"))
        self.assertIn("[OK]", err)

    def test_blocked_exits_1_with_hint_and_no_text(self):
        code, out, err, _ = run_cli(["b" * 11], [BLOCKED])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("[BLOCKED]", err)
        self.assertIn("hint:", err)

    def test_json(self):
        code, out, _, _ = run_cli(["--json", "a" * 11], [OK])
        d = json.loads(out)
        self.assertEqual((d["status"], d["retryable"]), (yt.OK, False))

    def test_apify_is_off_unless_flagged(self):
        _, _, _, called = run_cli(["a" * 11], [OK])
        self.assertFalse(called.call_args.kwargs["apify"])
        _, _, _, called = run_cli(["--apify", "--max-charge", "0.1", "a" * 11], [OK])
        self.assertTrue(called.call_args.kwargs["apify"])
        self.assertEqual(called.call_args.kwargs["max_charge_usd"], 0.1)

    def test_languages(self):
        _, _, _, called = run_cli(["--lang", "de, en", "a" * 11], [OK])
        self.assertEqual(called.call_args.args[1], ["de", "en"])


class Mcp(unittest.TestCase):
    def setUp(self):
        from yt_transcripts import mcp_server
        self.m = mcp_server

    def test_tools_registered(self):
        tools = asyncio.run(self.m.server.list_tools())
        tools = getattr(tools, "tools", tools)
        self.assertEqual(sorted(t.name for t in tools), ["get_transcript", "get_transcripts"])

    def test_paging(self):
        d = self.m.page({"text": "x" * 2500, "segments": [1]}, 0, 1000, False)
        self.assertEqual((len(d["text"]), d["next_offset"], d["total_chars"]), (1000, 1000, 2500))
        self.assertNotIn("segments", d)
        d = self.m.page({"text": "x" * 2500}, 2000, 1000, True)
        self.assertEqual((len(d["text"]), d["next_offset"]), (500, None))

    def test_bad_input_is_a_status_not_a_crash(self):
        d = self.m.get_transcript("not a video")
        self.assertEqual(d["status"], yt.ERROR)


if __name__ == "__main__":
    unittest.main()
