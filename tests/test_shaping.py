from __future__ import annotations

import unittest

from artek_buddy.db.shaping import (
    answer_ask_blocks,
    blocks_text,
    next_seq,
    older_cursor,
    preview_snippet,
    product_run_status,
    strip_markdown,
    text_blocks,
)


class ShapingTest(unittest.TestCase):
    def test_next_seq_starts_at_zero(self) -> None:
        self.assertEqual(next_seq(None), 0)
        self.assertEqual(next_seq(0), 1)
        self.assertEqual(next_seq(9), 10)

    def test_text_blocks_and_extract(self) -> None:
        blocks = text_blocks("hello")
        self.assertEqual(blocks, [{"kind": "text", "text": "hello"}])
        self.assertEqual(blocks_text(blocks), "hello")
        self.assertEqual(blocks_text([{"kind": "meta", "text": "note"}]), "note")
        self.assertEqual(blocks_text([{"kind": "file", "name": "notes.txt", "size": 4}]), "notes.txt")
        self.assertEqual(blocks_text([]), "")

    def test_preview_snippet(self) -> None:
        self.assertEqual(preview_snippet("  a   b  "), "a b")
        self.assertEqual(preview_snippet("**Белград, сейчас (11:30)**\n- +24.6°C"), "Белград, сейчас (11:30) +24.6°C")
        self.assertEqual(preview_snippet("# Header\n[YouTube](https://youtube.com) is `running`"), "Header YouTube is running")
        long = "x" * 200
        out = preview_snippet(long, limit=20)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 20)

    def test_strip_markdown(self) -> None:
        self.assertEqual(strip_markdown("```ts\ncode\n```hello"), "hello")
        self.assertEqual(strip_markdown("~~strike~~ and **bold** and *italic*"), "strike and bold and italic")
        self.assertEqual(strip_markdown("> quote\n1. item one"), "quote\nitem one")

    def test_older_cursor(self) -> None:
        self.assertIsNone(older_cursor([], 50))
        self.assertIsNone(older_cursor(list(range(10)), 50))
        self.assertEqual(older_cursor(list(range(50)), 50), 0)
        self.assertEqual(older_cursor(list(range(50, 100)), 50), 50)

    def test_answer_ask_blocks_marks_only_pending(self) -> None:
        pending = [
            {"kind": "ask", "text": "Which city?", "status": "pending", "actions": [{"id": "a", "label": "Belgrade"}]},
            {"kind": "text", "text": "ignore"},
        ]
        next_blocks, changed = answer_ask_blocks(pending, "Belgrade")
        self.assertTrue(changed)
        self.assertEqual(next_blocks[0]["status"], "answered")
        self.assertEqual(next_blocks[0]["answer"], "Belgrade")
        self.assertEqual(next_blocks[1], {"kind": "text", "text": "ignore"})
        again, changed_again = answer_ask_blocks(next_blocks, "Berlin")
        self.assertFalse(changed_again)
        self.assertEqual(again[0]["answer"], "Belgrade")
        empty, empty_changed = answer_ask_blocks(pending, "  ")
        self.assertFalse(empty_changed)
        self.assertEqual(empty, pending)
        consent = [
            {
                "kind": "ask",
                "text": "Open wikipedia.org?",
                "status": "pending",
                "consent_id": "cns_1",
                "actions": [{"id": "once", "label": "Allow once"}],
            }
        ]
        skipped, skip_changed = answer_ask_blocks(consent, "Allow once")
        self.assertFalse(skip_changed)
        self.assertEqual(skipped[0]["status"], "pending")
        marked, marked_changed = answer_ask_blocks(consent, "Allow once", include_consent=True)
        self.assertTrue(marked_changed)
        self.assertEqual(marked[0]["status"], "answered")

    def test_product_run_status(self) -> None:
        self.assertEqual(product_run_status("finished"), "completed")
        self.assertEqual(product_run_status("completed"), "completed")
        self.assertEqual(product_run_status("cancelled"), "cancelled")
        self.assertEqual(product_run_status("error"), "failed")
        self.assertEqual(product_run_status(None), "failed")
        self.assertNotEqual(product_run_status("finished"), "finished")


if __name__ == "__main__":
    unittest.main()
