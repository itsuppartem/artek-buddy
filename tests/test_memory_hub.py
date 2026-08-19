from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from artek_buddy.memory import wrap_turn_prompt
from artek_buddy.memory_gateway import GatewayClient, make_gateway_server
from artek_buddy.memory_hub import (
    InMemoryGateway,
    MemoryEntry,
    MemoryHub,
    extract_unwritten_memories,
    format_recalled_memory,
    is_expired,
    should_persist_ask,
)
from artek_buddy.runtime.tools import ProductTools


@dataclass
class _Doc:
    id: str
    scope: str
    bot_id: str | None
    path: str
    content: str


@dataclass
class _FakeStore:
    entries: list[MemoryEntry] = field(default_factory=list)
    documents: list[_Doc] = field(default_factory=list)
    _n: int = 0

    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}"

    def create_memory_entry(
        self,
        text: str,
        kind: str = "preference",
        scope: str = "user",
        bot_id: str | None = None,
        source: str = "remember",
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
        slot: str | None = None,
        shelf: str = "owner",
        until: str | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=self._next("ment"),
            scope=scope,
            kind=kind,
            text=text,
            source=source,
            bot_id=bot_id,
            document_id=self._next("mem"),
            slot=slot,
            shelf=shelf,
            until=until,
        )
        self.entries.append(entry)
        self.documents.append(
            _Doc(entry.document_id or entry.id, scope, bot_id if scope == "bot" else None, f"{kind}.md", text)
        )
        return entry

    def find_live_memory_entry(
        self,
        text: str,
        scope: str = "user",
        bot_id: str | None = None,
    ) -> MemoryEntry | None:
        for entry in self.entries:
            if entry.text != text or entry.scope != scope:
                continue
            if scope == "bot" and entry.bot_id != bot_id:
                continue
            return entry
        return None

    def find_live_memory_entry_by_slot(
        self,
        slot: str,
        scope: str = "user",
        bot_id: str | None = None,
    ) -> MemoryEntry | None:
        for entry in self.entries:
            if entry.slot != slot or entry.scope != scope:
                continue
            if scope == "bot" and entry.bot_id != bot_id:
                continue
            return entry
        return None

    def list_live_memory_entries(self, bot_id: str | None = None) -> list[MemoryEntry]:
        out: list[MemoryEntry] = []
        for entry in self.entries:
            if is_expired(entry):
                continue
            if entry.scope == "user" or (bot_id and entry.bot_id == bot_id):
                out.append(entry)
        return out

    def supersede_memory_entry(self, entry_id: str) -> bool:
        before = len(self.entries)
        self.entries = [entry for entry in self.entries if entry.id != entry_id]
        return len(self.entries) < before

    def find_entry_by_document(self, document_id: str) -> MemoryEntry | None:
        for entry in self.entries:
            if entry.document_id == document_id:
                return entry
        return None

    def update_entry_text(self, entry_id: str, text: str) -> MemoryEntry | None:
        for index, entry in enumerate(self.entries):
            if entry.id == entry_id:
                updated = replace(entry, text=text)
                self.entries[index] = updated
                return updated
        return None

    def attach_memory_entry(
        self,
        document: _Doc,
        kind: str = "preference",
        source: str = "panel",
        slot: str | None = None,
        shelf: str = "owner",
        until: str | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=self._next("ment"),
            scope=document.scope,
            kind=kind,
            text=document.content,
            source=source,
            bot_id=document.bot_id,
            document_id=document.id,
            slot=slot,
            shelf=shelf,
            until=until,
        )
        self.entries.append(entry)
        return entry

    def delete_memory(self, document_id: str) -> bool:
        self.entries = [entry for entry in self.entries if entry.document_id != document_id]
        before = len(self.documents)
        self.documents = [doc for doc in self.documents if doc.id != document_id]
        return len(self.documents) < before

    def memory_for_agent(self, bot_id: str) -> list[_Doc]:
        return [
            doc
            for doc in self.documents
            if doc.scope == "user" or doc.bot_id == bot_id
        ]


class MemoryHubTest(unittest.TestCase):
    def test_remember_appends_shared_and_other_bot_recalls(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        first = hub.capture("Prefers short answers", kind="preference", bot_id="bot_a")
        assert first is not None
        self.assertEqual(first.scope, "user")
        again = hub.capture("Prefers short answers", bot_id="bot_a")
        self.assertIsNone(again)
        context = hub.context_for_turn("bot_b", "how should answers look")
        assert context is not None
        self.assertIn("Prefers short answers", context)
        prompt = wrap_turn_prompt("how should answers look", context, role="lead")
        self.assertIn("Prefers short answers", prompt)
        self.assertIn("remember", prompt)
        self.assertTrue(prompt.endswith("how should answers look"))
        status = hub.context_for_turn("bot_b", "как там?")
        assert status is not None
        self.assertIn("Prefers short answers", status)

    def test_bot_scope_stays_in_that_chat(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        hub.capture("This research uses Wikipedia only", kind="rule", scope="bot", bot_id="bot_a")
        self.assertTrue(any("Wikipedia" in entry.text for entry in store.list_live_memory_entries("bot_a")))
        self.assertFalse(any("Wikipedia" in entry.text for entry in store.list_live_memory_entries("bot_b")))

    def test_ask_and_extract_and_forget(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        hub.capture("Belgrade", kind="choice", source="ask", question="Which city?", bot_id="bot_a", run_id="run_1")
        self.assertTrue(hub.captured_during("run_1"))
        self.assertIn("Belgrade", store.entries[0].text)
        self.assertEqual(store.entries[0].slot, "city")
        hub.extract_after_turn("I prefer tea", "run_1", "bot_a")
        self.assertTrue(any("tea" in entry.text.lower() for entry in store.entries))
        removed = hub.forget("forget the tea preference", bot_id="bot_a")
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(any("tea" in entry.text.lower() for entry in store.entries))

    def test_same_slot_replaces_old(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        hub.capture("Lives in Moscow", kind="place", slot="city", bot_id="bot_a")
        hub.capture("Lives in Belgrade", kind="place", slot="city", bot_id="bot_a")
        live = [entry.text for entry in store.list_live_memory_entries("bot_a")]
        self.assertEqual(live, ["Lives in Belgrade"])
        context = hub.context_for_turn("bot_b", "where do I live")
        assert context is not None
        self.assertIn("Belgrade", context)
        self.assertNotIn("Moscow", context)

    def test_skips_one_off_ask_and_extracts_a_short_phrase(self) -> None:
        self.assertFalse(should_persist_ask("Which tab should I open?", "Gmail"))
        self.assertTrue(should_persist_ask("Which city should we research?", "Belgrade"))
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        self.assertIsNone(
            hub.capture("Gmail", kind="choice", source="ask", question="Which tab?", bot_id="bot_a")
        )
        found = extract_unwritten_memories("I prefer tea, and also open gmail")
        self.assertEqual(found[0].kind, "preference")
        self.assertIn("tea", found[0].text.lower())
        self.assertNotIn("gmail", found[0].text.lower())
        found = extract_unwritten_memories("The user sent these messages while you were working. I prefer tea")
        self.assertEqual(found, [])

    def test_extract_heuristics(self) -> None:
        self.assertEqual(extract_unwritten_memories("hello"), [])
        self.assertEqual(extract_unwritten_memories("I prefer short briefs", already_saved=True), [])
        found = extract_unwritten_memories("I prefer short briefs")
        self.assertEqual(found[0].kind, "preference")
        self.assertEqual(extract_unwritten_memories("забудь про чай")[0].kind, "forget")
        self.assertEqual(extract_unwritten_memories("меня зовут Артём")[0].slot, "name")

    def test_format_recalled_memory_caps_bytes(self) -> None:
        rows = [
            MemoryEntry(id="a", scope="user", kind="preference", text="short", source="remember"),
            MemoryEntry(id="b", scope="user", kind="rule", text="never open the weather in a browser", source="remember"),
        ]
        text = format_recalled_memory(rows, [])
        assert text is not None
        self.assertIn("<durable_memory>", text)
        self.assertIn("preference: short", text)
        tiny = format_recalled_memory(rows, rows, max_bytes=80)
        assert tiny is not None
        self.assertLessEqual(len(tiny.encode("utf-8")), 80)

    def test_tone_and_format_do_not_clobber(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        hub.capture("без эмодзи", kind="preference", bot_id="bot_a")
        hub.capture("пиши коротко", kind="preference", bot_id="bot_a")
        live = store.list_live_memory_entries("bot_a")
        slots = {entry.slot: entry.text for entry in live}
        self.assertEqual(slots.get("tone"), "No emoji")
        self.assertEqual(slots.get("format"), "Prefers short answers")
        context = hub.context_for_turn("bot_a", "как там?")
        assert context is not None
        self.assertIn("## owner", context)
        self.assertIn("No emoji", context)
        self.assertIn("Prefers short answers", context)

    def test_three_shelves_and_expired_work_hidden(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())
        hub.capture("меня зовут Артём", kind="person", bot_id="bot_a")
        hub.capture(
            "This research uses Wikipedia only",
            kind="rule",
            scope="bot",
            bot_id="bot_a",
        )
        work = hub.capture(
            "repo artek-buddy on main this week",
            kind="project",
            bot_id="bot_a",
        )
        assert work is not None
        self.assertEqual(work.shelf, "work")
        self.assertIsNotNone(work.until)
        context = hub.context_for_turn("bot_a", "which repo and branch")
        assert context is not None
        self.assertIn("## owner", context)
        self.assertIn("## this bot", context)
        self.assertIn("## work", context)
        self.assertIn("Wikipedia", context)
        self.assertIn("artek-buddy", context)
        chit = hub.context_for_turn("bot_a", "как там?")
        assert chit is not None
        self.assertIn("Артём", chit)
        self.assertIn("Wikipedia", chit)
        self.assertNotIn("## work", chit)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        store.entries = [
            replace(entry, until=past) if entry.id == work.id else entry for entry in store.entries
        ]
        hub.gateway.entries = [
            replace(entry, until=past) if entry.id == work.id else entry
            for entry in hub.gateway.entries
        ]
        later = hub.context_for_turn("bot_a", "which repo and branch")
        assert later is not None
        self.assertNotIn("artek-buddy", later)

    def test_subagent_remember_stays_charter(self) -> None:
        store = _FakeStore()
        hub = MemoryHub(store, InMemoryGateway())

        class _Runtime:
            memory = hub
            store = None

            def resolve_turn_context(self, _bound: str | None = None) -> tuple[str, str, str]:
                return ("bot_a", "sub_1", "th_1")

            def resolve_turn_role(self, _bound: str | None = None) -> str:
                return "subagent"

        result = ProductTools(_Runtime()).execute(
            "remember",
            {"content": "This research uses Wikipedia only", "kind": "rule"},
            "bot_a",
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(store.entries[0].scope, "bot")
        self.assertEqual(store.entries[0].shelf, "charter")


class MemoryGatewayLoopbackTest(unittest.TestCase):
    def test_capture_recall_delete(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="artek-memory-gw-"))
        httpd = make_gateway_server(str(root), port=0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            port = httpd.server_address[1]
            client = GatewayClient(f"http://127.0.0.1:{port}")
            entry = MemoryEntry(
                id="ment_1",
                scope="user",
                kind="preference",
                text="Prefers tea",
                source="remember",
                bot_id="bot_a",
            )
            client.capture(entry, "owner", "bot_a")
            found = client.recall("owner", "tea", "bot_b", 8)
            self.assertTrue(any(item.text == "Prefers tea" for item in found))
            client.delete("ment_1")
            self.assertFalse(any(item.id == "ment_1" for item in client.recall("owner", "tea", "bot_b", 8)))
            local = MemoryEntry(
                id="ment_2",
                scope="bot",
                kind="rule",
                text="This research uses Wikipedia only",
                source="remember",
                bot_id="bot_a",
            )
            client.capture(local, "owner", "bot_a")
            leaked = client.recall("owner", "wikipedia", "bot_b", 8)
            self.assertFalse(any(item.id == "ment_2" for item in leaked))
            self.assertEqual(client.recall("owner", "", "bot_b", 8), [])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
