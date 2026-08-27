from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from artek_buddy.memory_book import (
    BOOK_SECTIONS,
    CHARTER_SECTIONS,
    MAX_BOT_INSTRUCTIONS,
    MAX_EXTRACT_CHARS,
    MAX_SECTION_CHARS,
    MAX_WORK,
    charter_book_entries,
    clean_rewrite,
    format_recalled_memory,
    infer_book_shelf,
    infer_section,
    merge_section,
    owner_book_entries,
    section_line,
)

log = logging.getLogger("artek_buddy")

ENTRY_KINDS = (
    "preference",
    "choice",
    "rule",
    "person",
    "project",
    "place",
    "desktop",
    "correction",
    "workflow",
)
SHELVES = ("owner", "work", "charter")
PROFILE_SLOTS = ("name", "city", "tz", "tone", "format", "language")
MAX_RECALL = 8
_TOKEN = re.compile(r"[a-zа-яё0-9]{2,}", re.IGNORECASE)
_PIECE = re.compile(r"[a-zа-яё]+|\d+", re.IGNORECASE)
_INBOX = "The user sent these messages"
_FORGET = re.compile(r"(?i)\b(forget|забудь|не помни|stop remembering)\b")
_ONE_OFF = re.compile(r"(?i)\b(open|открой|вкладк|tab|gmail|url|http|сейчас|this time|once)\b")
_DURABLE_ASK = re.compile(
    r"(?i)\b(city|город|name|зовут|timezone|часовой|prefer|язык|language|где жив)\b"
)
_EPHEMERAL_ASK = re.compile(
    r"(?i)\b(tab|вкладк|open|открой|file|файл|url|http|сейчас|this time|once)\b"
)
_STOPWORDS = {
    "the",
    "and",
    "for",
    "not",
    "this",
    "that",
    "with",
    "from",
    "forget",
    "забудь",
    "помни",
    "stop",
    "remembering",
    "please",
    "про",
    "для",
    "как",
    "там",
    "что",
    "это",
    "мне",
    "тебя",
    "еще",
    "ещё",
    "just",
    "about",
    "also",
}
_EXTRACT = (
    (
        re.compile(r"(?i)\b(?:my name is|меня зовут|зови меня)\s+([a-zа-яё][\w.\-]*)"),
        "person",
        "name",
        "Name is {0}",
    ),
    (
        re.compile(r"(?i)\b(?:timezone|часовой пояс|tz)\s*(?:is|[:=])?\s*([a-zA-Z_+\-0-9/]+)"),
        "place",
        "tz",
        "Timezone is {0}",
    ),
    (
        re.compile(r"(?i)\b(?:живу в|live in|город)\s+([a-zа-яё][\w.\-]*)"),
        "place",
        "city",
        "Lives in {0}",
    ),
    (
        re.compile(r"(?i)\b(без эмодзи|no emoji|без смайл)"),
        "preference",
        "tone",
        "No emoji",
    ),
    (
        re.compile(r"(?i)\b(пиши коротко|short answers|коротки[ей])"),
        "preference",
        "format",
        "Prefers short answers",
    ),
    (
        re.compile(r"(?i)\b(?:repo|репозитор\w*|ветк[аеуи]|branch)\s+[:=]?\s*(\S+)"),
        "project",
        None,
        "Project {0}",
    ),
    (
        re.compile(r"(?i)\b(?:i prefer|prefer|предпочит\w*)\s+(.+)"),
        "preference",
        None,
        "Prefers {0}",
    ),
    (
        re.compile(r"(?i)\b(?:never|always|don't|do not|не открывай|не ищи|не надо)\b(.+)?"),
        "rule",
        None,
        None,
    ),
)


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    scope: str
    kind: str
    text: str
    source: str
    bot_id: str | None = None
    document_id: str | None = None
    slot: str | None = None
    shelf: str = "owner"
    until: str | None = None


@dataclass(frozen=True)
class Extracted:
    kind: str
    text: str
    slot: str | None = None


class MemoryGateway(Protocol):
    def capture(self, entry: MemoryEntry, user_id: str, agent_id: str | None) -> None: ...
    def recall(
        self, user_id: str, query: str, agent_id: str | None, limit: int
    ) -> list[MemoryEntry]: ...
    def delete(self, entry_id: str) -> None: ...


class NullGateway:
    def capture(self, entry: MemoryEntry, user_id: str, agent_id: str | None) -> None:
        return None

    def recall(
        self, user_id: str, query: str, agent_id: str | None, limit: int
    ) -> list[MemoryEntry]:
        return []

    def delete(self, entry_id: str) -> None:
        return None


class InMemoryGateway:
    """Test double. Same verbs as the loopback sidecar."""

    def __init__(self) -> None:
        self.entries: list[MemoryEntry] = []

    def capture(self, entry: MemoryEntry, user_id: str, agent_id: str | None) -> None:
        self.entries = [item for item in self.entries if item.id != entry.id]
        self.entries.append(entry)

    def recall(
        self, user_id: str, query: str, agent_id: str | None, limit: int
    ) -> list[MemoryEntry]:
        wanted = query_tokens(query)
        hits = [
            entry
            for entry in self.entries
            if entry.scope != "bot" or entry.bot_id == agent_id
            if not wanted or wanted & tokens(f"{entry.kind} {entry.text}")
        ]
        return rank_entries(hits, query)[:limit]

    def delete(self, entry_id: str) -> None:
        self.entries = [item for item in self.entries if item.id != entry_id]


def normalize_kind(value: str | None) -> str:
    kind = (value or "preference").strip().lower()
    return kind if kind in ENTRY_KINDS else "preference"


def entry_path(entry_id: str, kind: str, shelf: str = "owner") -> str:
    layer = shelf if shelf in SHELVES else "owner"
    return f"entries/{layer}/{kind}-{entry_id}.md"


def shelf_from_path(path: str, scope: str = "user") -> str:
    match = re.match(r"^entries/(owner|work|charter)/", path or "")
    if match:
        return match.group(1)
    if scope == "bot":
        return "charter"
    return "owner"


def is_expired(entry: MemoryEntry, now: datetime | None = None) -> bool:
    if not entry.until:
        return False
    try:
        stamp = datetime.fromisoformat(entry.until)
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp <= (now or datetime.now(UTC))


def tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN.finditer(text or "")}


def query_tokens(text: str) -> set[str]:
    return tokens(text) - _STOPWORDS


def first_clause(text: str) -> str:
    part = re.split(r"(?i)\s+(?:and also|и ещё|и еще|а также)\s+", text or "", maxsplit=1)[0]
    part = re.split(r"[.;]\s+", part, maxsplit=1)[0]
    return " ".join(part.split()).strip(" ,")


def infer_slot(kind: str, text: str, slot: str | None = None) -> str | None:
    return infer_section(kind, text, slot)


def infer_shelf(scope: str, kind: str, slot: str | None, text: str) -> str:
    section = infer_section(kind, text, slot)
    return infer_book_shelf(scope, kind, section, text)


def infer_until(text: str, shelf: str, slot: str | None) -> str | None:
    if shelf in {"owner", "charter"} and slot in BOOK_SECTIONS:
        return None
    blob = text or ""
    now = datetime.now(UTC)
    if re.search(r"(?i)\b(this week|на этой неделе)\b", blob):
        return (now + timedelta(days=7)).isoformat()
    if re.search(r"(?i)\b(today|сегодня)\b", blob):
        return (now + timedelta(days=1)).isoformat()
    if re.search(r"(?i)\b(sprint|спринт)\b", blob):
        return (now + timedelta(days=14)).isoformat()
    return None


def should_persist_ask(question: str | None, answer: str) -> bool:
    blob = f"{question or ''} {answer or ''}"
    if _DURABLE_ASK.search(blob):
        return True
    if _EPHEMERAL_ASK.search(blob):
        return False
    return False


def shorten_memory(text: str, kind: str, slot: str | None) -> str:
    clause = first_clause(text)
    if not clause:
        return ""
    if _ONE_OFF.search(clause) and slot not in PROFILE_SLOTS:
        if infer_section(kind, clause, slot) not in BOOK_SECTIONS:
            return ""
    if slot == "name":
        match = re.search(r"(?i)(?:my name is|меня зовут|зови меня)\s+([a-zа-яё][\w.\-]*)", clause)
        if match:
            return f"Name is {match.group(1)}"
    if slot == "city":
        match = re.search(r"(?i)(?:живу в|live in|город)\s+([a-zа-яё][\w.\-]*)", clause)
        if match:
            return f"Lives in {match.group(1)}"
    if slot == "tone" and re.search(r"(?i)эмодзи|emoji", clause):
        return "No emoji"
    if slot == "format" and re.search(r"(?i)коротко|short", clause):
        return "Prefers short answers"
    if kind == "preference" and re.search(r"(?i)\b(?:i prefer|prefer|предпочит\w*)\s+(.+)", clause):
        rest = re.sub(r"(?i)^(?:i prefer|prefer|предпочит\w*)\s+", "", clause).strip(" .")
        if rest:
            return f"Prefers {rest[:80]}"
    return clause[:120]


def forget_matches(needle: set[str], entry_text: str) -> bool:
    hit = needle & (tokens(entry_text) - _STOPWORDS)
    return any(len(word) >= 3 for word in hit)


def similar_memory(left: str, right: str) -> bool:
    """True when two notes are the same fact worded differently.

    Distinct objects in the same template (site-0 vs site-4, Gmail vs Outlook)
    stay different. Short function words and stems (don't / do not, разрешения /
    разрешение) do not count as a new fact.
    """
    a = {
        w
        for w in (m.group(0).lower() for m in _PIECE.finditer(left or ""))
        if w not in _STOPWORDS and (w.isdigit() or len(w) >= 2)
    }
    b = {
        w
        for w in (m.group(0).lower() for m in _PIECE.finditer(right or ""))
        if w not in _STOPWORDS and (w.isdigit() or len(w) >= 2)
    }
    if not a or not b:
        return False
    overlap = a & b
    if len(overlap) < 2:
        return False
    if len(overlap) / len(a | b) < 0.6:
        return False
    leftover = a ^ b
    for word in leftover:
        if word.isdigit():
            return False
        if len(word) < 4:
            continue
        others = (a | b) - {word}
        if not any(_same_stem(word, other) for other in others):
            return False
    return True


def _same_stem(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 4:
        return False
    return left.startswith(right[:4]) or right.startswith(left[:4])


def rank_entries(entries: list[MemoryEntry], query: str) -> list[MemoryEntry]:
    wanted = query_tokens(query)
    if not wanted:
        return []
    scored: list[tuple[int, int, MemoryEntry]] = []
    for index, entry in enumerate(entries):
        overlap = len(wanted & tokens(f"{entry.kind} {entry.slot or ''} {entry.text}"))
        if overlap < 1:
            continue
        boost = 2 if entry.slot in BOOK_SECTIONS else 0
        scored.append((overlap + boost, -index, entry))
    scored.sort(reverse=True)
    return [item[2] for item in scored]


def extract_unwritten_memories(
    user_text: str,
    skipped_slots: set[str] | frozenset[str] = frozenset(),
    already_saved: bool = False,
) -> list[Extracted]:
    text = (user_text or "").strip()
    if already_saved or not text or text.startswith(_INBOX):
        return []
    if _FORGET.search(text):
        return [Extracted(kind="forget", text=text)]
    found: list[Extracted] = []
    seen_slots: set[str] = set()
    for pattern, kind, slot, template in _EXTRACT:
        match = pattern.search(text)
        if not match:
            continue
        if slot and (slot in skipped_slots or slot in seen_slots):
            continue
        clause = first_clause(match.group(0))
        if template and match.lastindex:
            body = template.format(first_clause(match.group(1)))
        elif template:
            body = template
        else:
            body = shorten_memory(clause, kind, slot)
        body = (body or "").strip()
        if not body or (
            _ONE_OFF.search(body) and infer_section(kind, body, slot) not in BOOK_SECTIONS
        ):
            continue
        found.append(
            Extracted(
                kind=kind, text=body[:MAX_EXTRACT_CHARS], slot=infer_section(kind, body, slot)
            )
        )
        if slot:
            seen_slots.add(slot)
    return found


class MemoryHub:
    """Postgres is the panel source of truth. The gateway is a search index."""

    def __init__(
        self,
        store: Any,
        gateway: MemoryGateway | None = None,
        user_id: str = "owner",
        rewriter: Any | None = None,
    ) -> None:
        self.store = store
        self.gateway = gateway or NullGateway()
        self.user_id = user_id
        self.rewriter = rewriter
        self._captures: dict[str, int] = {}
        self._slots: dict[str, set[str]] = {}
        self._bodies: dict[str, list[str]] = {}

    def captured_during(self, run_id: str | None) -> bool:
        return bool(run_id and self._captures.get(run_id, 0) > 0)

    def slots_during(self, run_id: str | None) -> set[str]:
        if not run_id:
            return set()
        return set(self._slots.get(run_id) or ())

    def capture(
        self,
        text: str,
        *,
        kind: str = "preference",
        scope: str = "user",
        bot_id: str | None = None,
        source: str = "remember",
        run_id: str | None = None,
        thread_id: str | None = None,
        question: str | None = None,
        slot: str | None = None,
    ) -> MemoryEntry | None:
        body = (text or "").strip()
        if not body:
            return None
        if kind == "forget" or (source == "extract" and _FORGET.search(body)):
            self.forget(body, bot_id=bot_id)
            return None
        if source == "ask" and not should_persist_ask(question, body):
            return None
        kind = normalize_kind(kind)
        if question:
            body = f"{question.strip()} → {body}"
        section = infer_section(kind, body, slot)
        if section in CHARTER_SECTIONS and bot_id:
            scope = "bot"
        else:
            scope = "bot" if scope == "bot" and bot_id else "user"
        shelf = infer_book_shelf(scope, kind, section, body)
        until = infer_until(body, shelf, section)
        if source != "panel":
            ready = section_line(body, kind, section, source=source)
            if not ready:
                return None
            body = ready
        if run_id:
            for prior in self._bodies.get(run_id, []):
                if similar_memory(prior, body):
                    self._mark_capture(run_id, section, body)
                    return None
        for live in self.store.list_live_memory_entries(bot_id=bot_id):
            if similar_memory(live.text, body):
                self._mark_capture(run_id, section, body)
                return None
        if self.store.find_live_memory_entry(body, scope=scope, bot_id=bot_id):
            self._mark_capture(run_id, section, body)
            return None
        previous = self.store.find_live_memory_entry_by_slot(section, scope=scope, bot_id=bot_id)
        if previous is not None:
            if similar_memory(previous.text, body):
                self._mark_capture(run_id, section, body)
                return None
            merged = merge_section(previous.text, body)
            if merged == previous.text:
                self._mark_capture(run_id, section, body)
                return None
            updated = self._revise(previous, merged, run_id, thread_id)
            self._mark_capture(run_id, section, body)
            if updated is not None:
                try:
                    self.gateway.capture(updated, self.user_id, bot_id)
                except Exception:
                    log.exception("memory gateway capture failed")
            return updated
        entry = self.store.create_memory_entry(
            text=body,
            kind=kind,
            scope=scope,
            bot_id=bot_id,
            source=source,
            source_run_id=run_id,
            source_thread_id=thread_id,
            slot=section,
            shelf=shelf,
            until=until,
        )
        try:
            self.gateway.capture(entry, self.user_id, bot_id)
        except Exception:
            log.exception("memory gateway capture failed")
        self._mark_capture(run_id, section, body)
        return entry

    def _revise(
        self,
        previous: MemoryEntry,
        text: str,
        run_id: str | None,
        thread_id: str | None,
    ) -> MemoryEntry | None:
        if previous.document_id and hasattr(self.store, "update_memory"):
            self.store.update_memory(
                previous.document_id,
                text,
                source_run_id=run_id,
                source_thread_id=thread_id,
            )
            found = self.store.find_entry_by_document(previous.document_id)
            if found is not None:
                return found
        return self.store.update_entry_text(previous.id, text)

    def _mark_capture(self, run_id: str | None, slot: str | None, body: str | None = None) -> None:
        if not run_id:
            return
        self._captures[run_id] = self._captures.get(run_id, 0) + 1
        if slot:
            self._slots.setdefault(run_id, set()).add(slot)
        if body:
            self._bodies.setdefault(run_id, []).append(body)

    def forget(self, text: str, bot_id: str | None = None) -> int:
        removed = 0
        needle = query_tokens(text)
        if not needle:
            return 0
        for entry in self.store.list_live_memory_entries(bot_id=bot_id):
            if not forget_matches(needle, entry.text):
                continue
            self.store.supersede_memory_entry(entry.id)
            try:
                self.gateway.delete(entry.id)
            except Exception:
                log.exception("memory gateway delete failed")
            removed += 1
        return removed

    def index_document(
        self,
        document: Any,
        *,
        kind: str = "preference",
        source: str = "panel",
    ) -> MemoryEntry | None:
        if document is None:
            return None
        body = str(getattr(document, "content", "") or "").strip()
        if not body:
            return None
        existing = self.store.find_entry_by_document(document.id)
        if existing is not None:
            updated = self.store.update_entry_text(existing.id, body) or existing
            try:
                self.gateway.capture(updated, self.user_id, updated.bot_id)
            except Exception:
                log.exception("memory gateway capture failed")
            return updated
        entry = self.store.attach_memory_entry(
            document,
            kind=normalize_kind(kind),
            source=source,
            slot=infer_section(kind, body),
        )
        try:
            self.gateway.capture(entry, self.user_id, entry.bot_id)
        except Exception:
            log.exception("memory gateway capture failed")
        return entry

    def remove_document(self, document_id: str) -> bool:
        entry = self.store.find_entry_by_document(document_id)
        deleted = self.store.delete_memory(document_id)
        if entry is not None:
            try:
                self.gateway.delete(entry.id)
            except Exception:
                log.exception("memory gateway delete failed")
        return deleted

    def context_for_turn(self, bot_id: str, query: str) -> str | None:
        live = [
            entry
            for entry in self.store.list_live_memory_entries(bot_id=bot_id)
            if not is_expired(entry)
        ]
        leftover = self._orphan_documents(bot_id, live)
        owner = owner_book_entries(live + leftover)
        charter = charter_book_entries(live, bot_id)
        charter.extend(self._bot_instructions(bot_id))
        wanted = query_tokens(query)
        work: list[MemoryEntry] = []
        if wanted:
            pool = [
                entry
                for entry in live + leftover
                if entry.shelf == "work" or entry.kind in {"project", "workflow"}
            ]
            work = rank_entries(pool or leftover, query)[:MAX_WORK]
            try:
                extra = self.gateway.recall(self.user_id, query, bot_id, MAX_RECALL)
            except Exception:
                log.exception("memory gateway recall failed")
                extra = []
            seen = {entry.id for entry in owner + charter + work}
            for item in extra:
                if is_expired(item):
                    continue
                if item.scope == "bot" and item.bot_id not in {None, bot_id}:
                    continue
                if item.shelf == "charter" and item.bot_id not in {None, bot_id}:
                    continue
                if item.id not in seen and (item.shelf == "work" or wanted & tokens(item.text)):
                    work.append(item)
                    seen.add(item.id)
                    if len(work) >= MAX_WORK:
                        break
        return format_recalled_memory(owner, charter, work)

    def _bot_instructions(self, bot_id: str) -> list[MemoryEntry]:
        getter = getattr(self.store, "get_bot", None)
        if getter is None:
            return []
        try:
            bot = getter(bot_id)
        except Exception:
            return []
        text = str(getattr(bot, "instructions", "") or "").strip()
        if not text:
            return []
        return [
            MemoryEntry(
                id=f"instr-{bot_id}",
                scope="bot",
                kind="rule",
                text=text[:MAX_BOT_INSTRUCTIONS],
                slot="purpose",
                source="bot",
                bot_id=bot_id,
                shelf="charter",
            )
        ]

    def _orphan_documents(self, bot_id: str, live: list[MemoryEntry]) -> list[MemoryEntry]:
        listed = getattr(self.store, "memory_for_agent", None)
        if listed is None:
            return []
        linked = {entry.document_id for entry in live if entry.document_id}
        finder = getattr(self.store, "find_entry_by_document", None)
        leftover: list[MemoryEntry] = []
        for document in listed(bot_id):
            if document.id in linked:
                continue
            if finder is not None and finder(document.id) is not None:
                continue
            scope_value = (
                document.scope.value if hasattr(document.scope, "value") else str(document.scope)
            )
            leftover.append(
                MemoryEntry(
                    id=document.id,
                    scope=scope_value,
                    kind="preference",
                    text=str(document.content or "")[:MAX_SECTION_CHARS],
                    source="document",
                    bot_id=document.bot_id,
                    document_id=document.id,
                    shelf=shelf_from_path(getattr(document, "path", "") or "", scope_value),
                )
            )
        return leftover

    def extract_after_turn(
        self, user_text: str, run_id: str | None, bot_id: str | None
    ) -> list[MemoryEntry]:
        saved: list[MemoryEntry] = []
        for item in extract_unwritten_memories(user_text, self.slots_during(run_id)):
            entry = self.capture(
                item.text,
                kind=item.kind,
                bot_id=bot_id,
                source="extract",
                run_id=run_id,
                slot=item.slot,
            )
            if entry is not None:
                saved.append(entry)
        return saved

    async def revise_after_turn(
        self, user_text: str, run_id: str | None, bot_id: str | None
    ) -> list[MemoryEntry]:
        already = self.slots_during(run_id)
        saved = self.extract_after_turn(user_text, run_id, bot_id)
        sections = self.slots_during(run_id)
        if not sections or self.rewriter is None:
            return saved
        fresh = extract_unwritten_memories(user_text)
        revised: list[MemoryEntry] = []
        for section in sections:
            scope = "bot" if section in CHARTER_SECTIONS else "user"
            entry = self.store.find_live_memory_entry_by_slot(section, scope=scope, bot_id=bot_id)
            if entry is None:
                continue
            extracted = "\n".join(item.text for item in fresh if item.slot == section)
            try:
                body = await self.rewriter.rewrite_section(
                    section, entry.text, user_text, extracted
                )
            except Exception:
                log.exception("memory book rewrite failed")
                continue
            ready = clean_rewrite(body)
            if not ready or ready == entry.text:
                continue
            updated = self._revise(entry, ready, run_id, None)
            if updated is None:
                continue
            try:
                self.gateway.capture(updated, self.user_id, bot_id)
            except Exception:
                log.exception("memory gateway capture failed")
            if (updated.slot or section) not in already:
                revised.append(updated)
        if revised:
            return revised
        return [entry for entry in saved if (entry.slot or "") not in already]
