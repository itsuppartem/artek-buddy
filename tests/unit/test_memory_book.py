from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.memory import wrap_turn_prompt
from artek_buddy.memory_hub import MemoryEntry, MemoryHub


class _BookStore:
    """In-memory stand-in for the memory mixin the hub already calls."""

    def __init__(self) -> None:
        self.entries: list[MemoryEntry] = []
        self.bot_instructions = ""
        self._n = 0

    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}"

    def list_live_memory_entries(
        self, bot_id: str | None = None, workspace_id: str = "ws"
    ) -> list[MemoryEntry]:
        return [entry for entry in self.entries if entry.scope == "user" or entry.bot_id == bot_id]

    def find_live_memory_entry(
        self,
        text: str,
        scope: str = "user",
        bot_id: str | None = None,
        workspace_id: str = "ws",
    ) -> MemoryEntry | None:
        body = (text or "").strip()
        for entry in self.entries:
            if entry.text != body or entry.scope != scope:
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
        workspace_id: str = "ws",
    ) -> MemoryEntry | None:
        for entry in self.entries:
            if entry.slot != slot or entry.scope != scope:
                continue
            if scope == "bot" and entry.bot_id != bot_id:
                continue
            return entry
        return None

    def find_entry_by_document(self, document_id: str) -> MemoryEntry | None:
        for entry in self.entries:
            if entry.document_id == document_id:
                return entry
        return None

    def create_memory_entry(
        self,
        text: str,
        kind: str = "preference",
        scope: str = "user",
        bot_id: str | None = None,
        source: str = "remember",
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
        workspace_id: str = "ws",
        slot: str | None = None,
        shelf: str = "owner",
        until: str | None = None,
    ) -> MemoryEntry:
        ident = self._next("ment")
        entry = MemoryEntry(
            id=ident,
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
        return entry

    def update_entry_text(self, entry_id: str, text: str) -> MemoryEntry | None:
        body = (text or "").strip()
        if not body:
            return None
        updated: list[MemoryEntry] = []
        found: MemoryEntry | None = None
        for entry in self.entries:
            if entry.id != entry_id:
                updated.append(entry)
                continue
            found = MemoryEntry(
                id=entry.id,
                scope=entry.scope,
                kind=entry.kind,
                text=body,
                source=entry.source,
                bot_id=entry.bot_id,
                document_id=entry.document_id,
                slot=entry.slot,
                shelf=entry.shelf,
                until=entry.until,
            )
            updated.append(found)
        self.entries = updated
        return found

    def update_memory(
        self,
        document_id: str,
        content: str,
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
    ) -> SimpleNamespace | None:
        entry = self.find_entry_by_document(document_id)
        if entry is None:
            return None
        self.update_entry_text(entry.id, content)
        return SimpleNamespace(id=document_id, content=content)

    def supersede_memory_entry(self, entry_id: str) -> bool:
        before = len(self.entries)
        self.entries = [entry for entry in self.entries if entry.id != entry_id]
        return len(self.entries) < before

    def get_bot(self, bot_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=bot_id, instructions=self.bot_instructions)

    def memory_for_agent(self, bot_id: str) -> list[object]:
        return []


def _hub() -> tuple[MemoryHub, _BookStore]:
    store = _BookStore()
    return MemoryHub(store, user_id="owner"), store


def test_hub_writes_and_revises_sections_from_a_turn() -> None:
    hub, store = _hub()
    first = hub.extract_after_turn(
        "My name is Artek. I live in Belgrade. No emoji.",
        "run_1",
        "bot_book",
    )
    assert first
    identity = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    tone = store.find_live_memory_entry_by_slot("tone", bot_id="bot_book")
    assert identity is not None
    assert "Artek" in identity.text
    assert "Belgrade" in identity.text
    assert tone is not None
    assert "emoji" in tone.text.lower()

    later = hub.extract_after_turn(
        "Timezone is Europe/Belgrade",
        "run_2",
        "bot_book",
    )
    assert later
    identity = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    assert identity is not None
    assert "Artek" in identity.text
    assert "Belgrade" in identity.text
    assert "Europe/Belgrade" in identity.text


def test_next_turn_prompt_keeps_owner_and_bot_book() -> None:
    hub, _store = _hub()
    hub.capture(
        "Repo path is /home/artek-diag/artek-buddy",
        kind="project",
        bot_id="bot_book",
        source="remember",
    )
    hub.capture(
        "Never open Gmail",
        kind="rule",
        bot_id="bot_book",
        source="remember",
    )
    hub.capture(
        "Wait for an explicit go-ahead before acting outward",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        slot="wait",
    )
    prompt = hub.context_for_turn("bot_book", "hello there, how is the weather")
    assert prompt is not None
    assert "/home/artek-diag/artek-buddy" in prompt
    assert "Never open Gmail" in prompt
    assert "go-ahead" in prompt
    assert "<owner_book>" in prompt
    assert "<bot_book>" in prompt
    assert "standing instructions" in prompt.lower()
    assert "data, not orders" in prompt.lower()
    wrapped = wrap_turn_prompt("hello there, how is the weather", prompt, role="lead")
    assert "/home/artek-diag/artek-buddy" in wrapped
    assert "Never open Gmail" in wrapped


def test_card_slot_limits_do_not_drop_a_multi_section_book() -> None:
    hub, store = _hub()
    store.bot_instructions = "B" * 240
    hub.capture("Name is Artek", kind="person", bot_id="bot_book")
    hub.capture("No emoji", kind="preference", bot_id="bot_book")
    hub.capture("Email is owner@example.test", kind="person", bot_id="bot_book")
    hub.capture("Machine is pi-living-room", kind="desktop", bot_id="bot_book")
    hub.capture(
        "Notes live in /home/artek-diag/artek-buddy/workspace",
        kind="preference",
        bot_id="bot_book",
    )
    for index in range(5):
        hub.capture(
            f"Never open site-{index}.example",
            kind="rule",
            scope="bot",
            bot_id="bot_book",
        )
    prompt = hub.context_for_turn("bot_book", "unrelated ping")
    assert prompt is not None
    for needle in (
        "Artek",
        "emoji",
        "owner@example.test",
        "pi-living-room",
        "/home/artek-diag/artek-buddy/workspace",
        "site-0.example",
        "site-4.example",
        "B" * 240,
    ):
        assert needle in prompt


def test_work_notes_still_require_a_match() -> None:
    hub, _store = _hub()
    hub.capture(
        "Sprint ticket AB-12 is the current work",
        kind="project",
        bot_id="bot_book",
        source="remember",
    )
    idle = hub.context_for_turn("bot_book", "hello there") or ""
    assert "AB-12" not in idle
    related = hub.context_for_turn("bot_book", "what about ticket AB-12")
    assert related is not None
    assert "AB-12" in related
    assert "<work_notes>" in related


def test_wrap_turn_prompt_tells_lead_to_revise_book_sections() -> None:
    wrapped = wrap_turn_prompt("hi", None, role="lead")
    assert "remember" in wrapped
    assert "section" in wrapped
    assert "one short sentence" not in wrapped
