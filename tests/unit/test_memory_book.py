from __future__ import annotations

from types import SimpleNamespace

import pytest

from artek_buddy.memory import MAX_AGENT_MEMORY_BYTES, wrap_turn_prompt
from artek_buddy.memory_book import HostBookRewriter, format_recalled_memory
from artek_buddy.memory_hub import (
    MemoryEntry,
    MemoryHub,
    extract_unwritten_memories,
    git_approval_contradicts,
    git_approval_same_rule,
    memory_covers,
    similar_memory,
)


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


def _hub(rewrite: bool = False) -> tuple[MemoryHub, _BookStore]:
    store = _BookStore()
    rewriter = HostBookRewriter(store) if rewrite else None
    return MemoryHub(store, user_id="owner", rewriter=rewriter), store


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


def test_extract_russian_city_sentences() -> None:
    belgrade = extract_unwritten_memories("Я живу в Белграде.")
    assert any("Белград" in item.text for item in belgrade)
    assert any(item.slot == "identity" for item in belgrade)
    novi = extract_unwritten_memories("Я живу в Нови-Саде.")
    assert any("Нови" in item.text for item in novi)


def test_remember_city_replaces_the_previous_city() -> None:
    hub, store = _hub()
    first = hub.capture(
        "Lives in Belgrade",
        kind="place",
        bot_id="bot_book",
        source="remember",
        slot="identity",
    )
    second = hub.capture(
        "Lives in Subotica",
        kind="place",
        bot_id="bot_book",
        source="remember",
        slot="identity",
    )
    assert first is not None
    assert second is not None
    identity = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    assert identity is not None
    assert "Subotica" in identity.text
    assert "Belgrade" not in identity.text
    assert len(store.list_live_memory_entries("bot_book")) == 1


def test_remember_replaces_near_matching_city_tokens() -> None:
    hub, store = _hub()
    first = hub.capture(
        "Lives in Cid28f7cdfda",
        kind="place",
        bot_id="bot_book",
        source="remember",
        slot="identity",
    )
    second = hub.capture(
        "Lives in Cid28f7cdfdb",
        kind="place",
        bot_id="bot_book",
        source="remember",
        slot="identity",
    )
    assert first is not None
    assert second is not None
    identity = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    assert identity is not None
    assert "Cid28f7cdfdb" in identity.text
    assert "Cid28f7cdfda" not in identity.text


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
    assert "once per fact" in wrapped
    assert "this-chat only" in wrapped


def test_similar_memory_paraphrase_not_a_different_ban() -> None:
    assert similar_memory("Do not ask permission for read", "Don't ask for read permission")
    assert similar_memory("не спрашивай разрешения на read", "не спрашивай разрешение на read")
    assert not similar_memory("Never open Gmail", "Never open Outlook")
    assert not similar_memory("Never open site-0.example", "Never open site-4.example")
    assert similar_memory("Lives in Cid28f7cdfda", "Lives in Cid28f7cdfdb")
    assert memory_covers(
        "Do not ask the owner for permission to work on this bot's computer or browser, "
        "or to run read-only commands on the owner's paired PC. Do not prompt.",
        "Don't ask for read permission",
    )
    assert not memory_covers("Don't ask for read permission", "Don't ask for write permission")
    assert not memory_covers("Never open Gmail for work", "Never open Outlook")


def test_git_approval_wait_and_ban_paraphrases_are_one_rule() -> None:
    long_rule = "Always ask before a git commit, a new branch, a pull request or MR, or a merge."
    assert git_approval_same_rule(long_rule, "Wait for MR approval.")
    assert git_approval_same_rule(long_rule, "Don't merge until I say so.")
    assert git_approval_same_rule("Wait for MR approval.", "Don't merge until I say so.")
    assert not git_approval_same_rule(long_rule, "You may merge and push without asking.")
    assert git_approval_contradicts(long_rule, "You may merge and push without asking.")
    assert not git_approval_same_rule(long_rule, "Never open Gmail")


def test_git_approval_restatements_do_not_add_a_second_row() -> None:
    hub, store = _hub()
    long_rule = "Always ask before a git commit, a new branch, a pull request or MR, or a merge."
    first = hub.capture(
        long_rule,
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_git_1",
        slot="wait",
    )
    mr = hub.capture(
        "Wait for MR approval.",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_git_2",
        slot="wait",
    )
    ban = hub.capture(
        "Don't merge until I say so.",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_git_3",
        slot="bans",
    )
    assert first is not None
    assert mr is None
    assert ban is None
    live = store.list_live_memory_entries("bot_book")
    assert len(live) == 1
    assert live[0].text == long_rule
    free = hub.capture(
        "You may merge and push without asking.",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_git_4",
        slot="bans",
    )
    assert free is not None
    after = store.list_live_memory_entries("bot_book")
    assert len(after) == 1
    assert "without asking" in after[0].text


def test_one_run_does_not_store_paraphrased_read_permission_twice() -> None:
    hub, store = _hub()
    first = hub.capture(
        "Do not ask permission for read",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_dup",
        slot="bans",
    )
    second = hub.capture(
        "Don't ask for read permission",
        kind="preference",
        scope="user",
        bot_id="bot_book",
        source="remember",
        run_id="run_dup",
    )
    assert first is not None
    assert second is None
    live = store.list_live_memory_entries("bot_book")
    assert len(live) == 1
    extra = hub.extract_after_turn(
        "Do not ask permission for read. Don't ask for read permission.",
        "run_dup",
        "bot_book",
    )
    assert extra == []
    assert len(store.list_live_memory_entries("bot_book")) == 1


def test_long_permission_ban_covers_a_shorter_later_restatement() -> None:
    hub, store = _hub()
    rule = (
        "Do not ask the owner for permission to work on this bot's computer or browser, "
        "or to run read-only commands on the owner's paired PC. Do not prompt."
    )
    first = hub.capture(
        rule,
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_first",
        slot="bans",
    )
    second = hub.capture(
        "Don't ask for read permission",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_later",
        slot="bans",
    )
    assert first is not None
    assert second is None
    live = store.list_live_memory_entries("bot_book")
    assert len(live) == 1
    assert live[0].text == rule


@pytest.mark.asyncio
async def test_revise_after_remember_does_not_add_another_row() -> None:
    hub, store = _hub(rewrite=True)
    saved = hub.capture(
        "Do not ask permission for read",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_dup",
        slot="bans",
    )
    assert saved is not None
    changed = await hub.revise_after_turn(
        "Do not ask permission for read",
        "run_dup",
        "bot_book",
    )
    assert changed == []
    assert len(store.list_live_memory_entries("bot_book")) == 1


@pytest.mark.asyncio
async def test_rewrite_replaces_a_contradiction_instead_of_appending() -> None:
    hub, store = _hub(rewrite=True)
    hub.extract_after_turn("My name is Artek. I live in Belgrade.", "run_1", "bot_book")
    await hub.revise_after_turn("I live in Subotica.", "run_2", "bot_book")
    identity = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    assert identity is not None
    assert "Artek" in identity.text
    assert "Subotica" in identity.text
    assert "Belgrade" not in identity.text
    prompt = hub.context_for_turn("bot_book", "hello there")
    assert prompt is not None
    assert "Subotica" in prompt
    assert "Belgrade" not in prompt


@pytest.mark.asyncio
async def test_idle_hello_does_not_rewrite_the_book() -> None:
    hub, store = _hub(rewrite=True)
    hub.extract_after_turn("My name is Artek. I live in Belgrade.", "run_1", "bot_book")
    before = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    assert before is not None
    changed = await hub.revise_after_turn("hello there", "run_idle", "bot_book")
    after = store.find_live_memory_entry_by_slot("identity", bot_id="bot_book")
    assert changed == []
    assert after is not None
    assert after.text == before.text


def test_two_do_not_rules_stay_two_cards_and_reassert_is_silent() -> None:
    hub, store = _hub()
    youtrack = "There is no YouTrack API token. Do not search for one or call YouTrack REST."
    git_rule = (
        "Before git/commit/branch/MR/merge on rn-robot, open_book git-commit-style "
        "and gitlab-mr-flow. Do not improvise MR descriptions."
    )
    first = hub.capture(
        youtrack,
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_spam",
        slot="do_not",
    )
    second = hub.capture(
        git_rule,
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_spam",
        slot="do_not",
    )
    again = hub.capture(
        youtrack + " Commenting needs the already-logged-in Chromium issue tab.",
        kind="rule",
        bot_id="bot_book",
        source="remember",
        run_id="run_spam",
        slot="do_not",
    )
    assert first is not None
    assert second is not None
    assert again is None
    live = store.list_live_memory_entries("bot_book")
    assert len(live) == 2
    blob = "\n".join(item.text for item in live)
    assert "YouTrack API token" in blob
    assert "git-commit-style" in blob
    assert hub.should_announce_remembered("run_spam", first.text) is True
    assert hub.should_announce_remembered("run_spam", first.text) is False
    assert hub.should_announce_remembered("run_spam", second.text) is True


def test_book_prompt_budget_fits_a_wide_chapter() -> None:
    assert MAX_AGENT_MEMORY_BYTES >= 256 * 1024
    chapter = "Keep the Pi notes on disk. " * 6000
    entry = MemoryEntry(
        id="ment_wide",
        scope="user",
        kind="preference",
        text=chapter,
        source="remember",
        bot_id="bot_book",
        slot="paths",
        shelf="owner",
    )
    prompt = format_recalled_memory([entry], [], [])
    assert prompt is not None
    assert "Keep the Pi notes on disk." in prompt
    assert len(prompt.encode("utf-8")) > 128 * 1024
