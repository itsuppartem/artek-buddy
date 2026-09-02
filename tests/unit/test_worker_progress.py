from __future__ import annotations

from artek_buddy.runtime.worker_progress import (
    format_progress_line,
    should_post_progress,
)


def test_format_progress_line_includes_remaining() -> None:
    assert (
        format_progress_line("commit", "push MR 76") == "Still working: commit. Next: push MR 76."
    )
    assert format_progress_line("commit") == "Still working: commit."
    assert format_progress_line("  ") == ""
    assert format_progress_line("commit", ["push MR 76", "comment on the ticket"]) == (
        "Still working: commit. Next: push MR 76, comment on the ticket."
    )


def test_format_progress_line_redacts_and_caps() -> None:
    line = format_progress_line("x" * 300, "y" * 300)
    assert len(line) < 500
    assert "xxx" in line


def test_should_post_progress_skips_identical_and_honors_floor() -> None:
    first = "Still working: commit. Next: push MR 76."
    second = "Still working: push MR 76. Next: comment on the ticket."
    assert should_post_progress(line=first, last_line=None, last_posted_at=None, now=10.0)
    assert not should_post_progress(
        line=first, last_line=first, last_posted_at=10.0, now=10.1, floor_s=0.2
    )
    assert not should_post_progress(
        line=second, last_line=first, last_posted_at=10.0, now=10.1, floor_s=0.2
    )
    assert should_post_progress(
        line=second, last_line=first, last_posted_at=10.0, now=10.3, floor_s=0.2
    )
    assert not should_post_progress(line="", last_line=None, last_posted_at=None, now=10.0)
