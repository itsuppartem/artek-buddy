from __future__ import annotations

import re
import unittest

from artek_buddy.auth import (
    PAIRING_ALPHABET,
    hash_secret,
    host_token_match,
    new_device_token,
    new_pairing_code,
    normalize_pairing_code,
)
from artek_buddy.__main__ import main as pair_main
from artek_buddy.contracts import PROCEDURES_BY_NAME, CreateDeviceInput, Device, DeviceCreated


class AuthHelpersTest(unittest.TestCase):
    def test_hash_secret_is_sha256_hex(self) -> None:
        digest = hash_secret("secret")
        self.assertEqual(len(digest), 64)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", digest))
        self.assertEqual(digest, hash_secret("secret"))
        self.assertNotEqual(digest, hash_secret("other"))

    def test_normalize_pairing_code(self) -> None:
        self.assertEqual(normalize_pairing_code("abcd-efgh"), "ABCDEFGH")
        self.assertEqual(normalize_pairing_code("  ab cd-ef gh  "), "ABCDEFGH")
        self.assertEqual(normalize_pairing_code("abcd@efgh"), "ABCDEFGH")

    def test_host_token_match_equal_length(self) -> None:
        self.assertTrue(host_token_match("same-token", "same-token"))
        self.assertFalse(host_token_match("same-token", "other-token"))

    def test_host_token_match_unequal_length(self) -> None:
        self.assertFalse(host_token_match("short", "much-longer-token"))
        self.assertFalse(host_token_match("much-longer-token", "short"))
        self.assertFalse(host_token_match("", "token"))
        self.assertFalse(host_token_match("token", ""))

    def test_new_device_token_shape(self) -> None:
        token = new_device_token()
        self.assertTrue(token.startswith("dev_"))
        self.assertGreaterEqual(len(token), 20)
        self.assertNotEqual(token, new_device_token())

    def test_new_pairing_code_shape(self) -> None:
        code = new_pairing_code()
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertTrue(all(ch in PAIRING_ALPHABET or ch == "-" for ch in code))
        self.assertEqual(len(normalize_pairing_code(code)), 8)


class DeviceContractTest(unittest.TestCase):
    def test_device_procedures_implemented(self) -> None:
        for name in (
            "devices.pairing",
            "devices.create",
            "devices.list",
            "devices.revoke",
        ):
            self.assertTrue(PROCEDURES_BY_NAME[name].implemented, name)
        self.assertEqual(PROCEDURES_BY_NAME["devices.pairing"].path, "/v1/devices/pairing")
        self.assertEqual(PROCEDURES_BY_NAME["devices.create"].output_model, "DeviceCreated")
        self.assertEqual(PROCEDURES_BY_NAME["devices.revoke"].method, "DELETE")

    def test_create_input_and_mint_response(self) -> None:
        body = CreateDeviceInput.model_validate(
            {"name": "desktop", "platform": "linux", "pairing_code": "ABCD-EFGH"}
        )
        self.assertEqual(body.pairing_code, "ABCD-EFGH")
        created = DeviceCreated.model_validate(
            {
                "id": "dev_1",
                "name": "desktop",
                "platform": "linux",
                "created_at": "2026-08-17T00:00:00Z",
                "token": "dev_shown_once",
            }
        )
        self.assertEqual(created.token, "dev_shown_once")
        listed = Device.model_validate(created.model_dump(exclude={"token"}))
        self.assertEqual(listed.id, "dev_1")
        self.assertNotIn("token", listed.model_dump())

    def test_pair_cli_usage(self) -> None:
        self.assertEqual(pair_main([]), 2)
        self.assertEqual(pair_main(["help"]), 2)


if __name__ == "__main__":
    unittest.main()
