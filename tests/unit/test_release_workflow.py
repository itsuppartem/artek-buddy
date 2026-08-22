from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_workflow_does_not_build_the_computer_image() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "artek-buddy-computer" not in text
    assert "Chromium under QEMU hangs" in text


def test_release_workflow_ships_sbom_attestations_and_changelog_notes() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "attestations: write" in text
    assert "attest-build-provenance" in text
    assert "sbom-client.cdx.json" in text
    assert "sbom-host.cdx.json" in text
    assert "cyclonedx" in text
    assert "python3 -m artek_buddy.release_notes" in text
    assert "--notes-file" in text
