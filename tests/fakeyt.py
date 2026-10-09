"""
A fake YouTube for the tests: a requests transport adapter that answers from
tests/fixtures. The real youtube-transcript-api code runs on top of it, so the
tests exercise the library's parsing and our classification together, offline.
"""
import os

import requests
from requests.adapters import BaseAdapter

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


class FakeYouTube(BaseAdapter):
    """routes: {"watch"|"player"|"timedtext": (status, fixture_name_or_bytes) or an exception}."""

    def __init__(self, **routes):
        super().__init__()
        self.routes = {"watch": (200, "watch.html"), "timedtext": (200, "transcript.xml")}
        self.routes.update(routes)
        self.calls = []

    def _route(self, url):
        if "/youtubei/v1/player" in url:
            return "player"
        if "/api/timedtext" in url:
            return "timedtext"
        if "/watch" in url:
            return "watch"
        raise AssertionError(f"unexpected URL in a test: {url}")

    def send(self, request, **kwargs):
        name = self._route(request.url)
        self.calls.append(name)
        spec = self.routes[name]
        if isinstance(spec, BaseException):
            raise spec
        status, body = spec
        r = requests.Response()
        r.status_code = status
        r.reason = {200: "OK", 403: "Forbidden", 429: "Too Many Requests",
                    500: "Internal Server Error"}.get(status, "")
        r._content = body if isinstance(body, bytes) else fixture(body)
        r.encoding = "utf-8"
        r.url = request.url
        r.request = request
        return r

    def close(self):
        pass


def session(**routes):
    s = requests.Session()
    adapter = FakeYouTube(**routes)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.adapter = adapter
    return s
