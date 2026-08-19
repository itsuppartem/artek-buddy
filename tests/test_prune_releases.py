from __future__ import annotations

import json
import unittest


def stale_tags(releases: list[dict[str, object]], keep: int = 5) -> list[str]:
    live = [row for row in releases if not row.get("isDraft")]
    live.sort(key=lambda row: str(row["createdAt"]), reverse=True)
    return [str(row["tagName"]) for row in live[keep:]]


class PruneReleasesTest(unittest.TestCase):
    def test_keeps_five_newest(self) -> None:
        rows = [
            {"tagName": f"v0.10.{n}", "createdAt": f"2026-08-{n:02d}T00:00:00Z", "isDraft": False}
            for n in range(18, 25)
        ]
        self.assertEqual(
            stale_tags(rows, 5),
            ["v0.10.19", "v0.10.18"],
        )

    def test_drafts_do_not_count(self) -> None:
        rows = [
            {"tagName": "v1", "createdAt": "2026-08-01T00:00:00Z", "isDraft": False},
            {"tagName": "draft", "createdAt": "2026-08-09T00:00:00Z", "isDraft": True},
        ]
        self.assertEqual(stale_tags(rows, 5), [])

    def test_fixture_matches_jq_keep_slice(self) -> None:
        raw = json.dumps(
            [
                {"tagName": "v2", "createdAt": "2026-08-02T00:00:00Z", "isDraft": False},
                {"tagName": "v1", "createdAt": "2026-08-01T00:00:00Z", "isDraft": False},
            ]
        )
        data = json.loads(raw)
        self.assertEqual(stale_tags(data, 1), ["v1"])


if __name__ == "__main__":
    unittest.main()
