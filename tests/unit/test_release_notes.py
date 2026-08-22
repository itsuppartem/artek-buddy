from __future__ import annotations

from pathlib import Path

import pytest

from artek_buddy.release_notes import changelog_section, render_release_notes

ROOT = Path(__file__).resolve().parents[2]

SAMPLE = """# Changelog

## Unreleased

### Added
- Not this release.

## [1.2.3] - 2026-08-01

### Fixed
- Pairing timeout.

### Added
- Host install script.

## [1.2.2] - 2026-07-01

### Changed
- Older notes.
"""


def test_changelog_section_is_the_named_version_only() -> None:
    body = changelog_section(SAMPLE, "1.2.3")
    assert body.startswith("## [1.2.3] - 2026-08-01")
    assert "Pairing timeout." in body
    assert "Host install script." in body
    assert "Unreleased" not in body
    assert "1.2.2" not in body


def test_changelog_section_missing_version_fails() -> None:
    with pytest.raises(ValueError, match="1.0.0"):
        changelog_section(SAMPLE, "1.0.0")


def test_render_release_notes_names_artifacts_and_limits() -> None:
    notes = render_release_notes("1.2.3", SAMPLE)
    assert "Pairing timeout." in notes
    assert "artek-buddy-client_1.2.3_all.deb" in notes
    assert "SHA256SUMS" in notes
    assert "sbom-client.cdx.json" in notes
    assert "sbom-host.cdx.json" in notes
    assert "gh attestation verify" in notes
    assert "Computer image is not built in Actions" in notes
    assert "Unreleased" not in notes


def test_repo_changelog_has_a_section_for_current_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    body = changelog_section(text, version)
    assert f"## [{version}]" in body
    assert "## Unreleased" not in body
