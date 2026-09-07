"""Search authorization and the indexed-text allow-list.

Grants (#157) are not in the tree. This module is the seam they fill:
the SQL query still receives an explicit resource id list and applies it
*before* ts_rank. Do not post-filter ranked rows in Python.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from artek_buddy.contracts.domain import Principal
from artek_buddy.observe import redact_text

SEARCH_DOCUMENT_KINDS = frozenset({"message", "memory", "artifact", "bot"})
SEARCH_INDEX_BLOCK_KINDS = frozenset({"text", "file"})
SEARCH_QUERY_MAX = 80
SEARCH_TOKEN_MAX = 8
SEARCH_LIMIT_MAX = 50
SEARCH_BODY_MAX = 8000
SEARCH_TIMEOUT_MS = 800
SEARCH_REBUILD_BATCH = 80
SEARCH_REBUILD_IDEMPOTENCY = "search.rebuild:0031"
SEARCH_HEADLINE_OPTIONS = "MaxWords=20, MinWords=5, StartSel=, StopSel=, HighlightAll=FALSE"


def authorized_search_resource_ids(
    principal: Principal,
    bot_ids: Iterable[str],
    workspace_id: str,
) -> list[str]:
    """Resource ids the principal may rank. Empty means no hits (deny-by-default)."""
    if principal.role != "owner":
        return []
    ids = [item for item in bot_ids if item]
    if workspace_id:
        ids.append(workspace_id)
    return ids


def normalize_search_query(raw: str | None) -> str:
    text = " ".join((raw or "").split())
    if not text:
        return ""
    if len(text) > SEARCH_QUERY_MAX:
        text = text[:SEARCH_QUERY_MAX].rstrip()
    tokens = [part for part in text.split() if part][:SEARCH_TOKEN_MAX]
    return " ".join(tokens)


def parse_search_kinds(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return sorted(SEARCH_DOCUMENT_KINDS)
    wanted: list[str] = []
    for part in str(raw).split(","):
        kind = part.strip().lower()
        if kind in SEARCH_DOCUMENT_KINDS and kind not in wanted:
            wanted.append(kind)
    return wanted


def cap_search_limit(raw: int | None) -> int:
    try:
        value = int(raw) if raw is not None else 20
    except (TypeError, ValueError):
        value = 20
    return max(1, min(value, SEARCH_LIMIT_MAX))


def searchable_message_text(blocks: Iterable[Any] | None) -> str:
    """Visible owner text and file names only. Never tool args or traces."""
    parts: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "")
        if kind not in SEARCH_INDEX_BLOCK_KINDS:
            continue
        if kind == "text":
            value = str(block.get("text") or "").strip()
        else:
            value = str(block.get("name") or "").strip()
        if value:
            parts.append(value)
    return " ".join(parts)


def index_body(text: str) -> str:
    cleaned = redact_text(text or "")
    if len(cleaned) > SEARCH_BODY_MAX:
        return cleaned[:SEARCH_BODY_MAX]
    return cleaned
