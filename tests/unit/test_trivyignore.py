from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IGNORE = ROOT / ".trivyignore"


def _cve_ids(text: str) -> set[str]:
    ids: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ids.add(stripped.split()[0])
    return ids


def test_trivyignore_names_unfixable_host_image_highs() -> None:
    text = IGNORE.read_text(encoding="utf-8")
    assert _cve_ids(text) >= {
        "CVE-2026-12151",
        "CVE-2026-1526",
        "CVE-2026-2229",
        "CVE-2026-56864",
        "CVE-2026-56865",
    }
    assert "cursor-sdk" in text
    assert "undici" in text
    assert "golang.org/x/mod" in text


def test_host_dockerfile_upgrades_fixed_python_highs() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "setuptools>=78.1.1" in text
    assert "msgpack>=1.2.1" in text


def test_threat_model_names_trivy_host_image_residuals() -> None:
    ghcr = next(
        line
        for line in (ROOT / "THREAT-MODEL.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| GHCR")
    )
    assert ".trivyignore" in ghcr
    assert "undici" in ghcr
    assert "golang.org/x/mod" in ghcr
