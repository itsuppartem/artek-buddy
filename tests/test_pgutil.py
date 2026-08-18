from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tests.pgutil import is_live_compose_url, require_test_db


class PgUtilTest(unittest.TestCase):
    def test_detects_live_compose_url(self) -> None:
        self.assertTrue(is_live_compose_url("postgresql://artek:artek@127.0.0.1:5432/artek_buddy"))
        self.assertTrue(is_live_compose_url("postgresql://artek:artek@localhost:5432/artek_buddy"))
        self.assertFalse(is_live_compose_url("postgresql://artek:artek@127.0.0.1:55432/artek_buddy_test"))
        self.assertFalse(is_live_compose_url("postgresql://artek:artek@127.0.0.1:5432/artek_buddy_test"))

    def test_require_skips_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_DATABASE_URL", None)
            with self.assertRaises(unittest.SkipTest):
                require_test_db()

    def test_require_refuses_live_url(self) -> None:
        with patch.dict(
            os.environ,
            {"TEST_DATABASE_URL": "postgresql://artek:artek@127.0.0.1:5432/artek_buddy"},
        ):
            with self.assertRaises(unittest.SkipTest):
                require_test_db()

    def test_require_accepts_throwaway_url(self) -> None:
        url = "postgresql://artek:artek@127.0.0.1:55432/artek_buddy_test"
        with patch.dict(os.environ, {"TEST_DATABASE_URL": url}):
            self.assertEqual(require_test_db(), url)


if __name__ == "__main__":
    unittest.main()
