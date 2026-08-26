from __future__ import annotations

import re
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from artek_buddy.contracts.domain import ComputerStatus
from artek_buddy.contracts.ids import BOT_COLORS

DEFAULT_PAGE_SIZE = 50
DEFAULT_WORKSPACE_ID = "ws_local"
DEFAULT_BOT_NAME = "artek-buddy"
PREVIEW_LIMIT = 120


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def next_seq(current_max: int | None) -> int:
    if current_max is None:
        return 0
    return int(current_max) + 1


def text_blocks(text: str) -> list[dict[str, str]]:
    return [{"kind": "text", "text": text}]


def blocks_text(blocks: Iterable[Any] | None) -> str:
    parts: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("kind")
        if kind in {"text", "meta", "progress", "computer", "plugin", "book"}:
            value = block.get("text")
            if value:
                parts.append(str(value))
        elif kind == "file":
            name = block.get("name")
            if name:
                parts.append(str(name))
        elif kind == "card":
            for line in block.get("lines") or []:
                if isinstance(line, dict):
                    parts.append(f"{line.get('k', '')}: {line.get('v', '')}".strip())
    return "\n".join(parts).strip()


def strip_markdown(text: str) -> str:
    if not text:
        return ""
    # Cap first so a long ask or user line cannot backtrack through these patterns.
    s = text[:4000]
    s = re.sub(r"```[\s\S]{0,2000}?```", "", s)
    s = re.sub(r"`([^`]{1,400})`", r"\1", s)
    s = re.sub(r"!\[([^\]\n]{0,200})\]\([^)\n]{1,400}\)", r"\1", s)
    s = re.sub(r"\[([^\]\n]{1,200})\]\([^)\n]{1,400}\)", r"\1", s)
    s = re.sub(r"(\*{1,3}|_{1,3})([^*_\n]{1,400})\1", r"\2", s)
    s = re.sub(r"~~([^~\n]{1,400})~~", r"\1", s)
    s = re.sub(r"(?m)^#{1,6}\s+", "", s)
    s = re.sub(r"(?m)^>\s*", "", s)
    s = re.sub(r"(?m)^(?:\s*[-*+]|\s*\d+\.)\s+", "", s)
    for _ in range(8):
        nxt = re.sub(r"<[^>\n]{0,256}>", "", s)
        if nxt == s:
            break
        s = nxt
    s = re.sub(r"[<>]", "", s)
    return s


def preview_snippet(text: str, limit: int = PREVIEW_LIMIT) -> str:
    cleaned = strip_markdown(text or "")
    compact = " ".join(cleaned.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def answer_ask_blocks(
    blocks: list[Any],
    answer: str,
    *,
    include_consent: bool = False,
) -> tuple[list[Any], bool]:
    text = (answer or "").strip()
    if not text or not isinstance(blocks, list):
        return blocks, False
    next_blocks: list[Any] = []
    changed = False
    for block in blocks:
        if (
            isinstance(block, dict)
            and block.get("kind") == "ask"
            and block.get("status") != "answered"
            and (include_consent or not block.get("consent_id"))
        ):
            next_blocks.append({**block, "status": "answered", "answer": text})
            changed = True
        else:
            next_blocks.append(block)
    return next_blocks, changed


def older_cursor(seqs: list[int], page_limit: int = DEFAULT_PAGE_SIZE) -> int | None:
    if not seqs or len(seqs) < page_limit:
        return None
    return min(seqs)


def product_run_status(sdk_status: str | None) -> str:
    value = (sdk_status or "").strip().lower()
    if value in {"finished", "completed", "complete", "success"}:
        return "completed"
    if value in {"cancelled", "canceled"}:
        return "cancelled"
    return "failed"


def isoformat_utc(value: datetime | None = None) -> str:
    moment = value or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(value: Any) -> str:
    if value is None:
        return isoformat_utc()
    if isinstance(value, datetime):
        return isoformat_utc(value)
    text = str(value)
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def pick_color(index: int) -> str:
    return BOT_COLORS[index % len(BOT_COLORS)]


def computer_stub(bot_id: str, mode: str = "team") -> ComputerStatus:
    return ComputerStatus(
        bot_id=bot_id,
        mode="dedicated" if mode == "dedicated" else "team",
        kind="desktop",
        state="running",
        control_holder="none",
        screen_available=False,
        home_revision=None,
        busy_bot_name=None,
    )
