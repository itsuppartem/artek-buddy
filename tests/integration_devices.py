#!/usr/bin/env python3
"""Device and pairing tables against a throwaway TEST_DATABASE_URL. No Cursor calls."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone

from artek_buddy.auth import hash_secret, new_pairing_code, normalize_pairing_code
from tests.pgutil import open_test_store


class DevicesIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = open_test_store()

    @classmethod
    def tearDownClass(cls) -> None:
        store = getattr(cls, "store", None)
        if store is not None:
            store.close()

    def test_tables_exist(self) -> None:
        with self.store._conn() as conn:
            rows = conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
            conn.commit()
        names = {row["table_name"] for row in rows}
        self.assertIn("devices", names)
        self.assertIn("device_pairing_codes", names)

    def test_mint_via_pairing_then_reject_reuse(self) -> None:
        pairing = self.store.create_pairing_code()
        self.addCleanup(
            self.store.delete_pairing_hash,
            hash_secret(normalize_pairing_code(pairing.code)),
        )
        self.assertRegex(pairing.code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertTrue(self.store.consume_pairing_code(pairing.code.lower()))
        self.assertFalse(self.store.consume_pairing_code(pairing.code))
        created = self.store.create_device("pairing-desktop", "linux")
        self.addCleanup(self.store.delete_device, created.id)
        self.assertTrue(created.token.startswith("dev_"))
        found = self.store.lookup_device_token(created.token)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, created.id)
        self.assertIsNotNone(found.last_seen_at)
        listed = {item.id: item for item in self.store.list_devices()}
        self.assertIn(created.id, listed)
        self.assertFalse(hasattr(listed[created.id], "token"))
        self.assertNotIn("token_hash", listed[created.id].model_dump())

    def test_expired_pairing_is_rejected(self) -> None:
        code = new_pairing_code()
        digest = hash_secret(normalize_pairing_code(code))
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        with self.store._conn() as conn:
            conn.execute(
                """
                INSERT INTO device_pairing_codes (code_hash, expires_at, created_at)
                VALUES (%s, %s, %s)
                """,
                (digest, past, past),
            )
            conn.commit()
        self.addCleanup(self.store.delete_pairing_hash, digest)
        self.assertFalse(self.store.consume_pairing_code(code))

    def test_mint_list_revoke_lookup(self) -> None:
        created = self.store.create_device("host-minted", "linux")
        self.addCleanup(self.store.delete_device, created.id)
        self.assertTrue(self.store.get_device(created.id))
        revoked = self.store.revoke_device(created.id)
        self.assertIsNotNone(revoked)
        assert revoked is not None
        self.assertIsNotNone(revoked.revoked_at)
        self.assertIsNone(self.store.lookup_device_token(created.token))
        again = self.store.revoke_device(created.id)
        assert again is not None
        self.assertEqual(again.revoked_at, revoked.revoked_at)
        self.assertIsNone(self.store.lookup_device_token("dev_missing_token"))
        self.assertIsNone(self.store.revoke_device("dev_missing"))


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Needs TEST_DATABASE_URL or make test-integration")
    unittest.main()
