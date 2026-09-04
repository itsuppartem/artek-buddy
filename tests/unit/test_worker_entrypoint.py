from __future__ import annotations

from artek_buddy.__main__ import USAGE, main


def test_worker_once_is_a_supported_entrypoint() -> None:
    """`python -m artek_buddy worker --once` must not be a usage error (#368)."""
    assert "worker" in USAGE
    assert main(["worker", "--once"]) != 2


def test_credential_services_are_documented_entrypoints() -> None:
    assert "credential-broker" in USAGE
    assert "credential-migrate" in USAGE
