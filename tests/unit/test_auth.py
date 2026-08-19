from __future__ import annotations

from artek_buddy.auth import (
    AttemptLimiter,
    derive_supervisor_token,
    host_token_match,
    normalize_pairing_code,
    supervisor_token,
)


def test_host_token_match_rejects_empty_and_wrong_length() -> None:
    assert host_token_match("", "abcdef") is False
    assert host_token_match("abc", "abcdef") is False
    assert host_token_match("abcdef", "abcdef") is True
    assert host_token_match("abcdeg", "abcdef") is False


def test_supervisor_token_is_not_the_host_token() -> None:
    host = "ci-host-token-aabbccddeeff001122334455"
    derived = derive_supervisor_token(host)
    assert derived != host
    assert supervisor_token(host, "") == derived
    assert supervisor_token(host, "explicit-supervisor") == "explicit-supervisor"


def test_pairing_limiter_blocks_after_limit() -> None:
    limiter = AttemptLimiter(limit=2, window_seconds=60)
    assert limiter.allow("1.1.1.1") is True
    limiter.record("1.1.1.1")
    limiter.record("1.1.1.1")
    assert limiter.allow("1.1.1.1") is False
    assert limiter.allow("2.2.2.2") is True


def test_normalize_pairing_code_strips_separators() -> None:
    assert normalize_pairing_code("ab12-cd34") == "AB12CD34"
    assert normalize_pairing_code("  ab12cd34  ") == "AB12CD34"
