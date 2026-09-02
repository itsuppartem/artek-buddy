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


def test_release_workflow_dispatch_requires_push_test_and_codeql_on_sha() -> None:
    """Dispatch must not publish a SHA whose push test or CodeQL is missing/red (#364)."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    bind = text.find("name: Bind release to one main SHA")
    detect = text.find("name: Detect VERSION bump")
    login = text.find("docker/login-action")
    assert bind != -1
    assert detect != -1
    assert login != -1
    bind_block = text[bind:detect]
    assert "--workflow test" in bind_block
    assert "--event push" in bind_block
    assert "check-runs" in bind_block
    assert "analyze (python)" in bind_block
    assert "analyze (javascript-typescript)" in bind_block
    assert '"CodeQL"' in bind_block or "'CodeQL'" in bind_block
    assert bind < login
    assert text.find("check-runs") < login


def test_release_workflow_prints_codeql_run_ids_before_publish() -> None:
    """Automatic path is gone; dispatch must still log CodeQL ids on github.sha (#366)."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    bind = text.find("name: Bind release to one main SHA")
    detect = text.find("name: Detect VERSION bump")
    promote = text.find("name: Promote scanned host image")
    release = text.find("name: GitHub Release")
    assert bind != -1
    assert detect != -1
    bind_block = text[bind:detect]
    assert "--workflow codeql" in bind_block
    assert "check_run_id=" in bind_block
    assert "codeql_run_id=" in bind_block
    assert bind < promote
    assert bind < release
    assert text.find("check-runs") < release
    assert text.find("check-runs") < promote


def test_release_workflow_force_cannot_reuse_a_published_version() -> None:
    """force=true on an existing tag/release must abort before registry write (#364)."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    refuse = text.find("name: Refuse a published VERSION")
    login = text.find("docker/login-action")
    push = text.find("name: Push host image digest")
    assert refuse != -1
    assert login != -1
    assert push != -1
    assert refuse < login
    assert refuse < push
    block = text[refuse:login]
    assert "ls-remote" in block
    assert "gh release view" in block
    assert "force cannot skip" in block
    assert "github.event.inputs.force" in text


def test_release_workflow_points_new_tag_at_tested_sha_before_ghcr_promote() -> None:
    """A missing tag must not be created from default develop (#359)."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    tag_step = text.find("name: Point release tag at the tested SHA")
    promote = text.find("name: Promote scanned host image")
    release = text.find("name: GitHub Release")
    assert tag_step != -1
    assert promote != -1
    assert release != -1
    assert tag_step < promote
    tag_block = text[tag_step:promote]
    assert "git tag" in tag_block
    assert "git push" in tag_block
    assert 'git rev-parse "${TAG}^{}"' in tag_block
    assert "RELEASE_SHA" in tag_block
    assert 'test "$PEELED" = "$RELEASE_SHA"' in tag_block
    create = text[release:]
    assert "gh release create" in create
    assert "--verify-tag" in create
    assert 'git rev-parse "${TAG}^{}"' in create
    assert 'test "$PEELED" = "$RELEASE_SHA"' in create
    assert release < promote


def test_release_workflow_serializes_and_promotes_after_github_release() -> None:
    """Overlapping dispatch must not both promote; GHCR tags wait for the Release (#365)."""
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    on_block = text.split("permissions:", 1)[0]
    assert "concurrency:" in on_block
    assert "cancel-in-progress: false" in on_block
    assert "cancel-in-progress: true" not in text
    checkout = text.find("actions/checkout@")
    login = text.find("docker/login-action")
    checkout_block = text[checkout:login]
    assert "persist-credentials: false" in checkout_block
    refuse = text.find("name: Refuse a published VERSION")
    imagetools = text.find("docker buildx imagetools create")
    release = text.find("name: GitHub Release")
    promote = text.find("name: Promote scanned host image")
    assert refuse != -1
    assert refuse < imagetools
    assert release != -1
    assert promote != -1
    assert release < promote
    assert "gh release create" in text[release:promote]


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
