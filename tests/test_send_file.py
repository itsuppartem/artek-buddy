from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from artek_buddy.config import Settings
from artek_buddy.runtime.tools import MAX_SEND_FILE_BYTES, ProductTools


def _settings(root: Path) -> Settings:
    return Settings(
        cursor_api_key="crsr_test_key",
        agent_http_token="test-token",
        agent_cwd=str(root / "cwd"),
        agent_data_dir=str(root / "data"),
    )


class _Store:
    def __init__(self, bot: SimpleNamespace) -> None:
        self.bot = bot
        self.artifacts: list[dict[str, object]] = []
        self.messages: list[list[object]] = []

    def get_bot(self, bot_id: str) -> SimpleNamespace | None:
        return self.bot if bot_id == self.bot.id else None

    def save_artifact(self, **kwargs: object) -> SimpleNamespace:
        self.artifacts.append(kwargs)
        return SimpleNamespace(id=kwargs.get("artifact_id") or "art_1")

    def append_bot_message(self, bot: object, blocks: list[object], run_id: str | None = None) -> SimpleNamespace:
        self.messages.append(blocks)
        return SimpleNamespace(id="msg_1", model_dump=lambda mode="json": {"id": "msg_1", "blocks": blocks})


class _Runtime:
    def __init__(self, settings: Settings, store: _Store) -> None:
        self.settings = settings
        self.store = store
        self.events = None
        self._sent: set[str] = set()

    def resolve_turn_context(self, bound_bot_id: str | None = None) -> tuple[str, str, str]:
        return bound_bot_id or self.store.bot.id, "run_1", "th_1"

    def home_cwd(self, bot_id: str | None = None) -> str:
        path = Path(self.settings.agent_data_dir) / "homes" / "team"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def mark_message_sent(self, run_id: str | None) -> None:
        if run_id:
            self._sent.add(run_id)


class SendFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="artek-send-file-"))
        self.bot = SimpleNamespace(id="bot_1", thread_id="th_1", workspace_id="ws_1", name="test")
        self.store = _Store(self.bot)
        self.runtime = _Runtime(_settings(self.root), self.store)
        self.tools = ProductTools(self.runtime)

    def test_send_file_from_home_path(self) -> None:
        home = Path(self.runtime.home_cwd(self.bot.id))
        (home / "report.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        out = self.tools.execute("send_file", {"path": "report.csv", "text": "Here is the CSV"})
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["name"], "report.csv")
        self.assertEqual(len(self.store.artifacts), 1)
        blocks = self.store.messages[0]
        self.assertEqual(blocks[0], {"kind": "text", "text": "Here is the CSV"})
        self.assertEqual(blocks[1]["kind"], "file")
        self.assertEqual(blocks[1]["name"], "report.csv")
        artifact_id = str(blocks[1]["artifact_id"])
        stored = self.root / "data" / "artifacts" / "bot_1" / artifact_id
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_text(encoding="utf-8"), "a,b\n1,2\n")

    def test_send_file_from_inline_content(self) -> None:
        out = self.tools.execute("send_file", {"path": "notes.txt", "content": "hello from the bot"})
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["name"], "notes.txt")
        self.assertEqual(self.store.messages[0][0]["kind"], "file")

    def test_send_file_rejects_outside_home(self) -> None:
        outside = self.root / "secret.txt"
        outside.write_text("nope", encoding="utf-8")
        out = self.tools.execute("send_file", {"path": str(outside)})
        self.assertFalse(out["ok"])
        self.assertIn("not found", out["error"])
        self.assertEqual(self.store.messages, [])

    def test_send_file_missing_path(self) -> None:
        out = self.tools.execute("send_file", {"path": "missing-notes.txt"})
        self.assertFalse(out["ok"])
        self.assertIn("not found", out["error"])
        self.assertEqual(self.store.messages, [])

    def test_send_file_rejects_empty(self) -> None:
        out = self.tools.execute("send_file", {})
        self.assertFalse(out["ok"])
        self.assertEqual(self.store.messages, [])

    def test_send_file_rejects_too_large(self) -> None:
        home = Path(self.runtime.home_cwd(self.bot.id))
        huge = home / "huge.bin"
        huge.write_bytes(b"x" * (MAX_SEND_FILE_BYTES + 1))
        out = self.tools.execute("send_file", {"path": "huge.bin"})
        self.assertFalse(out["ok"])
        self.assertIn("too large", out["error"])
        self.assertEqual(self.store.messages, [])
