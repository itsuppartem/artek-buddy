from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id

log = logging.getLogger("artek_buddy")

PAGE_KINDS = {"click", "type", "key", "down", "up", "scroll", "download", "fill", "submit", "press"}

MAX_SEND_FILE_BYTES = 25 * 1024 * 1024

MAX_INLINE_FILE_BYTES = 1 * 1024 * 1024

CONSENT_DONE = "The owner already answered the Allow card. Do not ask them to press Allow."

OWNER_STEER = (
    "The owner sent this while you were working. Apply it now. "
    "Do not finish the old plan first. Do not wait until this turn ends."
)


def format_owner_steer(items: list[dict[str, str | None]]) -> dict[str, Any] | None:
    texts = [str(item.get("text") or "").strip() for item in items]
    texts = [text for text in texts if text]
    if not texts:
        return None
    lines = [OWNER_STEER]
    for index, text in enumerate(texts, start=1):
        lines.append(f"{index}. {text}")
    return {"owner_follow_up": texts, "owner_instruction": "\n".join(lines)}


def _with_consent(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("denied") or payload.get("ok") is False:
        return payload
    out = dict(payload)
    out.setdefault("consent", "allowed")
    out.setdefault("note", CONSENT_DONE)
    return out


def _safe_filename(name: str) -> str:
    base = Path(str(name or "").strip()).name.replace("\x00", "").strip()
    return (base or "file")[:200]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _playwright_browser_command(actions: list[Any]) -> str:
    import json

    steps = []
    for item in actions:
        if isinstance(item, dict):
            steps.append(
                {
                    "kind": str(item.get("kind") or ""),
                    "url": str(item.get("url") or item.get("path") or ""),
                    "selector": str(item.get("selector") or ""),
                    "text": str(item.get("text") or ""),
                    "key": str(item.get("key") or ""),
                }
            )
    payload = json.dumps(steps)
    return (
        "python3 - <<'PY'\n"
        "import json, sys\n"
        "from playwright.sync_api import sync_playwright\n"
        f"STEPS = json.loads({payload!r})\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')\n"
        "    context = browser.contexts[0] if browser.contexts else browser.new_context()\n"
        "    page = context.pages[0] if context.pages else context.new_page()\n"
        "    for step in STEPS:\n"
        "        kind = step.get('kind')\n"
        "        if kind == 'goto' and step.get('url'):\n"
        "            page.goto(step['url'], wait_until='domcontentloaded')\n"
        "        elif kind == 'fill' and step.get('selector'):\n"
        "            page.fill(step['selector'], step.get('text') or '')\n"
        "        elif kind == 'click' and step.get('selector'):\n"
        "            page.click(step['selector'])\n"
        "        elif kind == 'type':\n"
        "            page.keyboard.type(step.get('text') or '')\n"
        "        elif kind == 'press':\n"
        "            page.keyboard.press(step.get('key') or 'Enter')\n"
        "        elif kind == 'submit':\n"
        "            sel = step.get('selector')\n"
        "            (page.locator(sel).press('Enter') if sel else page.keyboard.press('Enter'))\n"
        "    print(json.dumps({'ok': True, 'url': page.url, 'title': page.title()}))\n"
        "PY"
    )


def emit_computer_event(events: Any, bot: Any, status: Any) -> None:
    try:
        events.publish(
            ProductEvent(
                id=new_id("evt"),
                workspace_id=bot.workspace_id,
                thread_id=bot.thread_id,
                bot_id=bot.id,
                seq=events.next_seq(bot.id),
                type=ProductEventType.THREAD_COMPUTER,
                created_at=isoformat_utc(),
                payload=status.model_dump(mode="json"),
            )
        )
    except Exception:
        log.exception("failed to emit computer event")
