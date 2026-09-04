from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_named_codeql_residuals_keep_inline_lgtm() -> None:
    """Security-tab alerts stay named residuals, not forgotten holes (#367, #438)."""
    proxy = (ROOT / "client" / "proxy_rpc.py").read_text(encoding="utf-8")
    paths = (ROOT / "client" / "owner_paths.py").read_text(encoding="utf-8")
    jail = (ROOT / "src" / "artek_buddy" / "fs_jail.py").read_text(encoding="utf-8")
    creds = (ROOT / "src" / "artek_buddy" / "credential_broker.py").read_text(encoding="utf-8")
    runner = (ROOT / "src" / "artek_buddy" / "supervisor" / "credential_runner.py").read_text(
        encoding="utf-8"
    )
    threat = (ROOT / "THREAT-MODEL.md").read_text(encoding="utf-8")
    assert "lgtm[py/command-line-injection]" in proxy
    assert "lgtm[py/path-injection]" in paths
    assert "lgtm[py/path-injection]" in jail
    assert "codeql[py/path-injection]" in jail
    assert "contained_under" in runner
    assert "lgtm[py/clear-text-storage-sensitive-data]" in creds
    assert "codeql[py/clear-text-storage-sensitive-data]" in creds
    assert "py/command-line-injection" in threat
    assert "py/path-injection" in threat
    assert "py/clear-text-storage-sensitive-data" in threat
