from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_healthchecks_use_readyz() -> None:
    for name in (
        "docker-compose.yml",
        "docker-compose.release.yml",
        "docker-compose.ci.yml",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "8080/readyz" in text, name
        assert "8080/health')" not in text, name


def _service(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^volumes:\n)", text
    )
    assert match is not None, name
    return match.group(0)


def test_compose_isolates_credential_volume_and_migration() -> None:
    for name in ("docker-compose.yml", "docker-compose.release.yml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        broker = _service(text, "credential-broker")
        executor = _service(text, "credential-executor")
        migrator = _service(text, "credential-migrator")
        assert "127.0.0.1" in broker
        assert "credential-data:/var/lib/artek-buddy/credentials" in broker
        assert "./data/homes:/homes" not in broker
        assert "./data:/data" not in broker
        assert "env_file:" not in broker
        assert "AGENT_HTTP_TOKEN:" in broker
        assert "./data/homes:/homes" in executor
        assert "credential-data:" not in executor
        assert "./data:/data" not in executor
        assert "env_file:" not in executor
        assert "network_mode: none" in migrator
        assert "./data/credentials:/legacy-credentials" in migrator
        assert "credential-data:/var/lib/artek-buddy/credentials" in migrator
        assert 'CREDENTIAL_EXECUTOR_TOKEN: ""' in _service(text, "artek-buddy")
        for service in ("artek-buddy", "worker", "supervisor", "memory-gateway"):
            assert "credential-data:" not in _service(text, service)
        for service in ("worker", "supervisor"):
            block = _service(text, service)
            assert 'CREDENTIAL_BROKER_TOKEN: ""' in block
            assert 'CREDENTIAL_EXECUTOR_TOKEN: ""' in block
        assert "credential-data:" in text.partition("volumes:")[-1]
    ci = (ROOT / "docker-compose.ci.yml").read_text(encoding="utf-8")
    assert "ci-credential:/var/lib/artek-buddy/credentials" in _service(ci, "credential-broker")
    assert "ci-credential:" not in _service(ci, "artek-buddy")
    assert "ci-credential:" not in _service(ci, "supervisor")
    assert "ci-credential:" not in _service(ci, "credential-executor")
    assert 'CREDENTIAL_EXECUTOR_TOKEN: ""' in _service(ci, "artek-buddy")
    assert 'CREDENTIAL_BROKER_TOKEN: ""' in _service(ci, "supervisor")
    assert 'CREDENTIAL_EXECUTOR_TOKEN: ""' in _service(ci, "supervisor")
