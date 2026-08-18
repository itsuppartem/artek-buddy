from __future__ import annotations

import unittest
from unittest.mock import patch

from artek_buddy.computer.proxy import fetch_novnc


class _Response:
    status = 200
    headers = {"Content-Type": "text/html"}

    def read(self) -> bytes:
        return b"<html>noVNC</html>"

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class NovncProxyTest(unittest.TestCase):
    def test_retries_a_port_that_is_still_starting(self) -> None:
        with (
            patch(
                "artek_buddy.computer.proxy.urllib.request.urlopen",
                side_effect=[OSError("connection refused"), _Response()],
            ) as urlopen,
            patch("artek_buddy.computer.proxy.time.sleep") as sleep,
        ):
            response = fetch_novnc("http://127.0.0.1:6080/embed.html", "GET")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"<html>noVNC</html>")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()

    def test_unreachable_port_returns_html_not_json(self) -> None:
        with (
            patch(
                "artek_buddy.computer.proxy.urllib.request.urlopen",
                side_effect=OSError("connection refused"),
            ),
            patch("artek_buddy.computer.proxy.time.monotonic", side_effect=[0.0, 20.0]),
            patch("artek_buddy.computer.proxy.time.sleep"),
        ):
            response = fetch_novnc("http://127.0.0.1:6080/embed.html", "GET")

        self.assertEqual(response.status_code, 502)
        self.assertIn("text/html", response.media_type or "")
        self.assertIn(b"data-artek-screen-error", response.body)
        self.assertNotIn(b'"detail"', response.body)
