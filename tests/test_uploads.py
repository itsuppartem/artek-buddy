from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from artek_buddy.contracts import ThreadSendInput
from artek_buddy.memory import wrap_turn_prompt
from artek_buddy.uploads import (
    MAX_UPLOAD_FILES,
    UploadError,
    excerpt_text,
    format_user_turn,
    ingest_uploads,
    preview_for_upload,
    remove_bot_inbox_copies,
    unique_inbox_path,
    user_file_blocks,
    validate_batch,
)


class _Store:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []
        self.paths: dict[str, str] = {}
        self.rows: dict[str, SimpleNamespace] = {}

    def save_artifact(self, **kwargs: object) -> SimpleNamespace:
        artifact_id = str(kwargs.get("artifact_id") or f"art_{len(self.saved) + 1}")
        row = SimpleNamespace(
            id=artifact_id,
            bot_id=kwargs["bot_id"],
            name=kwargs["name"],
            mime_type=kwargs["mime_type"],
            size=kwargs["size"],
        )
        self.saved.append(kwargs)
        self.paths[artifact_id] = str(kwargs["storage_path"])
        self.rows[artifact_id] = row
        return row

    def get_artifact(self, artifact_id: str) -> tuple[SimpleNamespace, str] | None:
        row = self.rows.get(artifact_id)
        if row is None:
            return None
        return row, self.paths[artifact_id]


class UploadsTest(unittest.TestCase):
    def test_inbox_path_stays_in_inbox(self) -> None:
        from artek_buddy.uploads import inbox_path_under_home

        root = Path(tempfile.mkdtemp(prefix="artek-inbox-"))
        home = root / "home"
        (home / "inbox").mkdir(parents=True)
        secret = root / "secret.txt"
        secret.write_text("nope", encoding="utf-8")
        self.assertIsNone(inbox_path_under_home(home, "inbox/../secret.txt"))
        self.assertIsNone(inbox_path_under_home(home, "/etc/passwd"))
        self.assertIsNone(inbox_path_under_home(home, "Downloads/x.txt"))

    def test_unique_inbox_names(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="artek-inbox-"))
        inbox = root / "inbox"
        inbox.mkdir()
        (inbox / "notes.txt").write_text("one", encoding="utf-8")
        dest = unique_inbox_path(inbox, "notes.txt")
        self.assertEqual(dest.name, "notes-2.txt")

    def test_validate_rejects_too_many_and_empty(self) -> None:
        with self.assertRaises(UploadError):
            validate_batch([{"size": 1} for _ in range(MAX_UPLOAD_FILES + 1)])
        with self.assertRaises(UploadError):
            validate_batch([{"size": 0, "name": "empty.txt"}])

    def test_excerpt_only_for_small_text(self) -> None:
        self.assertEqual(excerpt_text("n.txt", "text/plain", b"hello"), "hello")
        self.assertIsNone(excerpt_text("shot.png", "image/png", b"\x89PNG"))
        self.assertIsNone(excerpt_text("big.txt", "text/plain", b"x" * (32 * 1024 + 1)))

    def test_format_user_turn_lists_paths(self) -> None:
        prompt = format_user_turn(
            "look",
            [
                {
                    "name": "notes.txt",
                    "path": "inbox/notes.txt",
                    "mime_type": "text/plain",
                    "size": 5,
                    "excerpt": "hello",
                }
            ],
        )
        self.assertIn("look", prompt)
        self.assertIn("inbox/notes.txt", prompt)
        self.assertIn("hello", prompt)

    def test_user_blocks_and_preview(self) -> None:
        hosted = [{"id": "art_1", "name": "a.txt", "mime_type": "text/plain", "size": 3}]
        blocks = user_file_blocks("", hosted)
        self.assertEqual(blocks[0]["kind"], "file")
        self.assertEqual(preview_for_upload("", hosted), "a.txt")

    def test_send_allows_files_without_text(self) -> None:
        raw = base64.b64encode(b"hello").decode("ascii")
        send = ThreadSendInput.model_validate(
            {"text": "", "attachments": [{"name": "n.txt", "content_base64": raw}]}
        )
        self.assertEqual(len(send.attachments), 1)
        with self.assertRaises(Exception):
            ThreadSendInput.model_validate({"text": "   "})

    def test_ingest_writes_artifact_and_inbox(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="artek-upload-"))
        home = root / "home"
        data_dir = root / "data"
        store = _Store()
        raw = base64.b64encode(b"hello from owner").decode("ascii")
        hosted = ingest_uploads(
            store=store,
            home=home,
            data_dir=data_dir,
            bot_id="bot_1",
            files=[{"name": "notes.txt", "content_base64": raw, "mime_type": "text/plain"}],
        )
        self.assertEqual(len(hosted), 1)
        self.assertEqual(hosted[0]["path"], "inbox/notes.txt")
        self.assertEqual((home / "inbox" / "notes.txt").read_text(encoding="utf-8"), "hello from owner")
        artifact_id = hosted[0]["id"]
        stored = data_dir / "artifacts" / "bot_1" / artifact_id
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_bytes(), b"hello from owner")
        self.assertTrue((data_dir / "artifacts" / "bot_1" / f"{artifact_id}.inbox").is_file())

    def test_delete_removes_this_chats_inbox_copy_only(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="artek-upload-"))
        home = root / "home"
        data_dir = root / "data"
        store = _Store()
        raw = base64.b64encode(b"from this chat").decode("ascii")
        hosted = ingest_uploads(
            store=store,
            home=home,
            data_dir=data_dir,
            bot_id="bot_gone",
            files=[{"name": "shot.jpeg", "content_base64": raw, "mime_type": "image/jpeg"}],
        )
        keep = home / "inbox" / "other.txt"
        keep.write_text("belongs to another team bot", encoding="utf-8")
        removed = remove_bot_inbox_copies(home, data_dir, "bot_gone", store.rows.values())
        self.assertEqual(removed, ["inbox/shot.jpeg"])
        self.assertFalse((home / "inbox" / "shot.jpeg").exists())
        self.assertEqual(keep.read_text(encoding="utf-8"), "belongs to another team bot")
        self.assertTrue((data_dir / "artifacts" / "bot_gone" / hosted[0]["id"]).is_file())

    def test_lead_prompt_mentions_inbox(self) -> None:
        text = wrap_turn_prompt("hello", None, role="lead")
        self.assertIn("inbox/", text)


if __name__ == "__main__":
    unittest.main()
