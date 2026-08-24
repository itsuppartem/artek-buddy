from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Names GitHub posts on a PR (job id, or CodeQL from github-advanced-security).
REQUIRED_MERGE_CHECKS = (
    "quality",
    "backend",
    "ui",
    "scan",
    "live_gate",
    "analyze (python)",
    "analyze (javascript-typescript)",
    "CodeQL",
)


def test_contributing_names_the_develop_and_main_merge_gate() -> None:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Protect develop" in text
    assert "Protect main" in text
    for name in REQUIRED_MERGE_CHECKS:
        assert name in text
    assert "`live` is not required" in text
    assert "develop is not branch-protected" not in text


def test_codeowners_does_not_claim_develop_is_unprotected() -> None:
    text = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "not branch-protected" not in text
    assert "Protect develop" in text


def test_release_workflow_comment_lists_the_full_merge_gate() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'ruleset "Protect main"' in text
    for name in ("quality", "backend", "ui", "scan", "live_gate"):
        assert name in text
    assert "analyze (python)" in text
    assert "live is not required" in text
