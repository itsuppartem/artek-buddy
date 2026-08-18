from __future__ import annotations

import unittest

from tests.ui_host import is_live_http_url, refuse_live_stack


class UiIsolationTest(unittest.TestCase):
    def test_live_http_port_is_the_compose_host(self) -> None:
        self.assertTrue(is_live_http_url("http://127.0.0.1:8080"))
        self.assertTrue(is_live_http_url("http://localhost:8080/"))
        self.assertTrue(is_live_http_url("https://funnel.example.ts.net"))
        self.assertFalse(is_live_http_url("http://127.0.0.1:18080"))

    def test_refuses_live_database_and_host(self) -> None:
        with self.assertRaises(SystemExit):
            refuse_live_stack(
                "postgresql://artek:artek@127.0.0.1:5432/artek_buddy",
                "http://127.0.0.1:18080",
            )
        with self.assertRaises(SystemExit):
            refuse_live_stack(
                "postgresql://artek:artek@127.0.0.1:55433/artek_buddy_ui",
                "http://127.0.0.1:8080",
            )
        refuse_live_stack(
            "postgresql://artek:artek@127.0.0.1:55433/artek_buddy_ui",
            "http://127.0.0.1:18080",
        )
