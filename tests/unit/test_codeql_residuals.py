from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_named_codeql_residuals_keep_inline_lgtm() -> None:
    """Security-tab alerts #8 and #11 stay named residuals, not forgotten holes (#367)."""
    proxy = (ROOT / "client" / "proxy.py").read_text(encoding="utf-8")
    paths = (ROOT / "client" / "owner_paths.py").read_text(encoding="utf-8")
    threat = (ROOT / "THREAT-MODEL.md").read_text(encoding="utf-8")
    assert "lgtm[py/command-line-injection]" in proxy
    assert "lgtm[py/path-injection]" in paths
    assert "py/command-line-injection" in threat
    assert "py/path-injection" in threat
