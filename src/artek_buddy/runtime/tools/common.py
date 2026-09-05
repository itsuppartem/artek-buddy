from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.status_ping import STATUS_PING_GUIDE

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
    lines = [
        OWNER_STEER,
        STATUS_PING_GUIDE,
        "If this is a correction, use steer_subagent on the same worker. "
        "Do not stop and spawn a replacement.",
    ]
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
        "SITE_CHROME = ['geolocation', 'notifications', 'clipboard-read', "
        "'clipboard-write', 'camera', 'microphone']\n"
        "def grant_site_chrome(context, page):\n"
        "    origin = (page.url or '').split('/', 3)\n"
        "    if len(origin) < 3 or origin[0] not in ('http:', 'https:'):\n"
        "        return\n"
        "    try:\n"
        "        context.grant_permissions(SITE_CHROME, origin='/'.join(origin[:3]))\n"
        "    except Exception:\n"
        "        pass\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=15000)\n"
        "    context = browser.contexts[0] if browser.contexts else browser.new_context()\n"
        "    def select_target_page(ctx, steps):\n"
        "        pages = ctx.pages\n"
        "        if not pages:\n"
        "            return ctx.new_page()\n"
        "        target_url = next((s['url'] for s in steps if s.get('url')), None)\n"
        "        if target_url:\n"
        "            for p in pages:\n"
        "                if target_url in (p.url or '') or ((p.url or '') and (p.url or '') in target_url):\n"
        "                    try:\n"
        "                        p.bring_to_front()\n"
        "                    except Exception:\n"
        "                        pass\n"
        "                    return p\n"
        "        for p in pages:\n"
        "            try:\n"
        "                if p.evaluate('() => !document.hidden'):\n"
        "                    p.bring_to_front()\n"
        "                    return p\n"
        "            except Exception:\n"
        "                pass\n"
        "        try:\n"
        "            pages[-1].bring_to_front()\n"
        "        except Exception:\n"
        "            pass\n"
        "        return pages[-1]\n"
        "    page = select_target_page(context, STEPS)\n"
        "    page.set_default_timeout(15000)\n"
        "    grant_site_chrome(context, page)\n"
        "    try:\n"
        "        for step in STEPS:\n"
        "            kind = step.get('kind')\n"
        "            if kind == 'goto' and step.get('url'):\n"
        "                page.goto(step['url'], wait_until='domcontentloaded', timeout=15000)\n"
        "                grant_site_chrome(context, page)\n"
        "            elif kind == 'fill' and step.get('selector'):\n"
        "                page.fill(step['selector'], step.get('text') or '', timeout=15000)\n"
        "            elif kind == 'click' and step.get('selector'):\n"
        "                page.click(step['selector'], timeout=15000)\n"
        "            elif kind == 'type':\n"
        "                page.keyboard.type(step.get('text') or '')\n"
        "            elif kind == 'press':\n"
        "                page.keyboard.press(step.get('key') or 'Enter')\n"
        "            elif kind == 'submit':\n"
        "                sel = step.get('selector')\n"
        "                (page.locator(sel).press('Enter', timeout=15000) if sel else page.keyboard.press('Enter'))\n"
        "        print(json.dumps({'ok': True, 'url': page.url, 'title': page.title()}))\n"
        "    except Exception as exc:\n"
        "        print(json.dumps({'ok': False, 'error': str(exc), 'url': getattr(page, 'url', ''), 'title': ''}))\n"
        "        sys.exit(1)\n"
        "PY"
    )


def emit_computer_event(events: Any, bot: Any, status: Any) -> None:
    try:
        payload = status.model_dump(mode="json")
        payload["status"] = status.state
        events.publish(
            ProductEvent(
                id=new_id("evt"),
                workspace_id=bot.workspace_id,
                thread_id=bot.thread_id,
                bot_id=bot.id,
                seq=events.next_seq(bot.id),
                type=ProductEventType.COMPUTER_STATUS,
                created_at=isoformat_utc(),
                payload=payload,
            )
        )
    except Exception:
        log.exception("failed to emit computer event")
