from __future__ import annotations

import unittest

from artek_buddy.auth import derive_supervisor_token, supervisor_token


class SupervisorTokenTest(unittest.TestCase):
    def test_derived_token_is_not_the_host_token(self) -> None:
        host = "host-secret-token"
        derived = derive_supervisor_token(host)
        self.assertEqual(len(derived), 64)
        self.assertNotEqual(derived, host)
        self.assertEqual(derived, derive_supervisor_token(host))

    def test_explicit_supervisor_token_wins(self) -> None:
        self.assertEqual(supervisor_token("host-secret", "explicit-supervisor"), "explicit-supervisor")
        self.assertEqual(supervisor_token("host-secret", "  "), derive_supervisor_token("host-secret"))
        self.assertEqual(supervisor_token("host-secret", ""), derive_supervisor_token("host-secret"))


if __name__ == "__main__":
    unittest.main()
