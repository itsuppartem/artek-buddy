from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.status_ping import STATUS_PING_GUIDE

log = logging.getLogger("artek_buddy")

PAGE_KINDS = {
    "click",
    "type",
    "key",
    "down",
    "up",
    "scroll",
    "download",
    "fill",
    "submit",
    "press",
    "evaluate",
    "eval",
}

BROWSER_ACT_KINDS = (
    "goto",
    "fill",
    "click",
    "click_all",
    "scroll",
    "type",
    "press",
    "submit",
    "evaluate",
    "eval",
    "extract",
    "text",
    "read",
    "get_text",
    "wait",
    "sleep",
    "hover",
)

BROWSER_ACT_PAGE_KINDS = frozenset(BROWSER_ACT_KINDS) - {"goto"}

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


def _normalize_browser_actions(
    actions: list[Any],
) -> tuple[list[dict[str, Any]], str | None]:
    steps: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            return [], "browser_act action must be an object"
        kind = str(item.get("kind") or "").strip().lower()
        if not kind:
            return [], "browser_act kind is empty"
        if kind not in BROWSER_ACT_KINDS:
            return [], f"unknown browser_act kind {kind!r}"
        expression = str(item.get("expression") or item.get("script") or item.get("js") or "")
        if kind in {"evaluate", "eval"} and not expression:
            fields = ", ".join(sorted(str(key) for key in item))
            return [], f"evaluate without expression/script/js (fields {fields})"
        direction = str(item.get("direction") or "").lower()
        clicks = int(item.get("clicks") or 3)
        delta_y = item.get("delta_y")
        if delta_y is None:
            delta_y = item.get("dy")
        if delta_y is not None:
            dy = int(delta_y)
        elif direction == "up":
            dy = -int(item.get("distance") or clicks * 100)
        elif direction == "down":
            dy = int(item.get("distance") or clicks * 100)
        else:
            dy = 0
        steps.append(
            {
                "kind": kind,
                "url": str(item.get("url") or item.get("path") or ""),
                "selector": str(item.get("selector") or ""),
                "text": str(item.get("text") or ""),
                "key": str(item.get("key") or ""),
                "delta_x": int(item.get("delta_x") or item.get("dx") or 0),
                "delta_y": dy,
                "direction": direction,
                "force": bool(item.get("force", False)),
                "all": bool(item.get("all", False)),
                "ms": int(item.get("ms") or item.get("timeout") or 1000),
                "attribute": str(item.get("attribute") or item.get("attr") or ""),
                "expression": expression,
            }
        )
    return steps, None


def _browser_act_fail_command(error: str) -> str:
    import json

    payload = json.dumps({"ok": False, "error": error}, ensure_ascii=False)
    return f"python3 - <<'PY'\nimport json, sys\nprint({payload!r})\nsys.exit(1)\nPY"


def _playwright_browser_command(actions: list[Any]) -> str:
    import json

    steps, error = _normalize_browser_actions(actions)
    if error:
        return _browser_act_fail_command(error)
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
        "    step_data = []\n"
        "    try:\n"
        "        for step in STEPS:\n"
        "            kind = str(step.get('kind') or '').lower()\n"
        "            if kind == 'goto' and step.get('url'):\n"
        "                page.goto(step['url'], wait_until='domcontentloaded', timeout=15000)\n"
        "                grant_site_chrome(context, page)\n"
        "            elif kind == 'fill' and step.get('selector'):\n"
        "                page.fill(step['selector'], step.get('text') or '', timeout=15000)\n"
        "            elif kind in ('click', 'click_all') and step.get('selector'):\n"
        "                sel = step['selector']\n"
        "                force = bool(step.get('force'))\n"
        "                click_all = bool(step.get('all') or kind == 'click_all')\n"
        "                if click_all:\n"
        "                    loc = page.locator(sel)\n"
        "                    count = loc.count()\n"
        "                    for i in range(count):\n"
        "                        try:\n"
        "                            loc.nth(i).click(timeout=3000, force=force)\n"
        "                        except Exception:\n"
        "                            try:\n"
        "                                loc.nth(i).evaluate('el => el.click()')\n"
        "                            except Exception:\n"
        "                                pass\n"
        "                    step_data.append({'kind': kind, 'clicked': count})\n"
        "                else:\n"
        "                    try:\n"
        "                        page.click(sel, timeout=15000, force=force)\n"
        "                    except Exception:\n"
        "                        page.locator(sel).first.evaluate('el => el.click()')\n"
        "                    step_data.append({'kind': kind, 'ok': True})\n"
        "            elif kind == 'scroll':\n"
        "                dx = int(step.get('delta_x') or 0)\n"
        "                dy = int(step.get('delta_y') or 0)\n"
        "                if not dy and not dx:\n"
        "                    direction = str(step.get('direction') or 'down').lower()\n"
        "                    dy = -500 if direction == 'up' else 500\n"
        "                sel = step.get('selector')\n"
        "                if sel:\n"
        "                    loc = page.locator(sel).first\n"
        "                    loc.scroll_into_view_if_needed(timeout=15000)\n"
        "                    if dx or dy:\n"
        "                        loc.evaluate('(el, [x, y]) => el.scrollBy(x, y)', [dx, dy])\n"
        "                else:\n"
        "                    page.mouse.wheel(dx, dy)\n"
        "                    page.evaluate('([x, y]) => window.scrollBy(x, y)', [dx, dy])\n"
        "                step_data.append({'kind': kind, 'dx': dx, 'dy': dy})\n"
        "            elif kind in ('evaluate', 'eval'):\n"
        "                if not step.get('expression'):\n"
        "                    raise RuntimeError('evaluate without expression/script/js')\n"
        "                res = page.evaluate(step['expression'])\n"
        "                step_data.append({'kind': kind, 'result': res})\n"
        "            elif kind in ('text', 'extract', 'read', 'get_text'):\n"
        "                sel = step.get('selector')\n"
        "                attr = step.get('attribute')\n"
        "                if sel:\n"
        "                    loc = page.locator(sel)\n"
        "                    cnt = loc.count()\n"
        "                    if attr:\n"
        "                        items = [loc.nth(i).get_attribute(attr) for i in range(min(cnt, 100))]\n"
        "                    else:\n"
        "                        items = [loc.nth(i).inner_text().strip() for i in range(min(cnt, 100))]\n"
        "                    step_data.append({'kind': kind, 'selector': sel, 'count': cnt, 'items': items})\n"
        "                else:\n"
        "                    step_data.append({'kind': kind, 'text': page.inner_text('body')[:50000]})\n"
        "            elif kind in ('wait', 'sleep'):\n"
        "                ms = min(int(step.get('ms') or 1000), 15000)\n"
        "                sel = step.get('selector')\n"
        "                if sel:\n"
        "                    page.wait_for_selector(sel, timeout=ms)\n"
        "                else:\n"
        "                    page.wait_for_timeout(ms)\n"
        "                step_data.append({'kind': kind, 'ms': ms})\n"
        "            elif kind == 'hover' and step.get('selector'):\n"
        "                page.locator(step['selector']).first.hover(timeout=10000)\n"
        "                step_data.append({'kind': kind, 'ok': True})\n"
        "            elif kind == 'type':\n"
        "                page.keyboard.type(step.get('text') or '')\n"
        "            elif kind == 'press':\n"
        "                page.keyboard.press(step.get('key') or 'Enter')\n"
        "            elif kind == 'submit':\n"
        "                sel = step.get('selector')\n"
        "                (page.locator(sel).press('Enter', timeout=15000) if sel else page.keyboard.press('Enter'))\n"
        "            else:\n"
        "                raise RuntimeError('unknown or skipped browser_act kind %r' % kind)\n"
        "        out = {'ok': True, 'url': page.url, 'title': page.title()}\n"
        "        if step_data:\n"
        "            out['data'] = step_data\n"
        "            eval_items = [s['result'] for s in step_data if 'result' in s]\n"
        "            text_items = [s['items'] for s in step_data if 'items' in s]\n"
        "            if eval_items:\n"
        "                out['result'] = eval_items[0] if len(eval_items) == 1 else eval_items\n"
        "            elif text_items:\n"
        "                out['result'] = text_items[0] if len(text_items) == 1 else text_items\n"
        "            elif any('text' in s for s in step_data):\n"
        "                out['result'] = next(s['text'] for s in step_data if 'text' in s)\n"
        "        print(json.dumps(out, ensure_ascii=False))\n"
        "    except Exception as exc:\n"
        "        print(json.dumps({'ok': False, 'error': str(exc), 'url': getattr(page, 'url', ''), 'title': ''}, ensure_ascii=False))\n"
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
