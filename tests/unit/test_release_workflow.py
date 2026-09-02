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


def test_release_workflow_scans_host_digest_before_promoting_latest() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    trivy = text.find("name: Trivy host image")
    promote = text.find("name: Promote scanned host image")
    assert trivy != -1
    assert promote != -1
    assert trivy < promote
    assert "artek-buddy:latest" not in text[:trivy]
    assert "artek-buddy:latest" in text[promote:]
    assert "push-by-digest=true" in text
    assert "ghcr.io/itsuppartem/artek-buddy@${{ steps.image.outputs.digest }}" in text
    host_scan = text[trivy:promote]
    assert "HIGH,CRITICAL" in host_scan or "CRITICAL,HIGH" in host_scan
    assert "docker buildx imagetools create" in text[promote:]


def test_release_workflow_does_not_clobber_release_assets() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "--clobber" not in text
    assert "gh release upload" not in text
    assert "gh release create" in text
    assert "refusing to replace existing GitHub Release" in text


def test_release_workflow_does_not_prune_github_releases() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "prune-releases.sh" not in text
    assert "Keep five GitHub Releases" not in text


def test_release_workflow_yaml_is_not_loaded_from_default_branch_workflow_run() -> None:
    """A develop-only release.yml change must not receive the write token (#358)."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    on_block = text.split("permissions:", 1)[0]
    assert "workflow_run:" not in on_block
    assert "workflow_dispatch:" in on_block
    assert "github.ref == 'refs/heads/main'" in text
    assert "github.workflow_sha" in text
    assert "merge-base --is-ancestor" in text
    assert "workflow_sha=" in text
    assert "released_sha=" in text
    assert "test_sha=" in text


def test_release_client_sbom_covers_the_packaged_deb() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "dpkg-deb -x" in text
    assert "scan-ref: client" not in text
    assert "artek-client-deb" in text


def test_contributing_treats_release_prune_as_manual() -> None:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Only the five newest Releases stay" not in text
    assert "infra/prune-releases.sh" in text
    assert "manual" in text.lower()
    prune = (ROOT / "infra" / "prune-releases.sh").read_text(encoding="utf-8")
    assert "Manual operator script" in prune
    assert "release.yml does not run this" in prune
