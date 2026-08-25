from __future__ import annotations

from typing import Any

ASKED_YOU_MARK = "asked you this:"
ASK_REPLY_MARK = "replied:"
MAX_REPLY_CHARS = 8000


class BotAskError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def find_inbox_bot(store: Any, ref: str) -> Any | None:
    key = str(ref or "").strip()
    if not key:
        return None
    found = store.get_bot(key)
    if found is not None:
        if getattr(found, "archived_at", None):
            return None
        return found
    matches = [item for item in store.list_bots() if item.name == key]
    return matches[0] if matches else None


def resolve_ask(store: Any, source: Any, text: str, dest_ref: str) -> Any:
    question = str(text or "").strip()
    if not question:
        raise BotAskError(400, "text is required")
    dest = find_inbox_bot(store, dest_ref)
    if dest is None:
        raise BotAskError(404, "bot not found")
    if dest.id == source.id:
        raise BotAskError(400, "a bot cannot message itself")
    return dest


def inbound_visible_text(from_name: str, question: str) -> str:
    return f"Bot {from_name} asked: {question}".strip()


def inbound_model_prompt(from_name: str, question: str) -> str:
    return (
        "Do the work in this chat. Your last message is the reply they will use "
        "to answer the owner. Do not copy their whole thread. Do not call "
        "message_bot to send the reply — finishing this turn sends it.\n\n"
        f"Bot {from_name} {ASKED_YOU_MARK} {question}".strip()
    )


def ready_visible_text(from_name: str) -> str:
    return f"{from_name} is ready."


def reply_model_prompt(from_name: str, answer: str) -> str:
    return (
        "Use this to answer the owner. Do not repeat their whole chat or their "
        "tool work.\n\n"
        f"Bot {from_name} {ASK_REPLY_MARK} {answer}".strip()
    )


def asked_card_blocks(dest: Any, question: str) -> list[dict[str, Any]]:
    return [
        {"kind": "text", "text": f"Asked {dest.name}: {question}"},
        {
            "kind": "child_bot",
            "bot_id": dest.id,
            "name": dest.name,
            "title": question,
            "status": "created",
        },
    ]


def ready_card_blocks(dest: Any) -> list[dict[str, Any]]:
    return [
        {"kind": "meta", "text": ready_visible_text(dest.name)},
        {
            "kind": "child_bot",
            "bot_id": dest.id,
            "name": dest.name,
            "title": "Replied",
            "status": "created",
        },
    ]


def _block_data(block: Any) -> dict[str, Any] | None:
    if hasattr(block, "model_dump"):
        data = block.model_dump()
        return data if isinstance(data, dict) else None
    return block if isinstance(block, dict) else None


def text_from_blocks(blocks: list[Any] | None) -> str:
    parts: list[str] = []
    for block in blocks or []:
        data = _block_data(block)
        if data is None:
            continue
        kind = str(data.get("kind") or "")
        if kind in {"computer", "progress", "subagent"}:
            continue
        if kind == "text" and data.get("text"):
            parts.append(str(data["text"]))
    return "\n".join(parts).strip()


def last_bot_reply(messages: list[Any], limit: int = MAX_REPLY_CHARS) -> str:
    cap = max(1, int(limit))
    for message in reversed(messages or []):
        role = getattr(message, "role", None)
        role_text = role.value if hasattr(role, "value") else str(role or "")
        if role_text != "bot":
            continue
        text = text_from_blocks(getattr(message, "blocks", None))
        if text:
            return text[:cap]
    return ""


def format_other_bots(bots: list[Any], current_id: str) -> str:
    names = [item.name for item in bots if getattr(item, "id", None) != current_id]
    if not names:
        return ""
    listed = ", ".join(names)
    return (
        "Other inbox bots you can ask by exact name or id: "
        f"{listed}. Use message_bot. Their last message comes back here; "
        "you answer the owner. Do not paste their thread."
    )
