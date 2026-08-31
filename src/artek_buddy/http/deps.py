from __future__ import annotations

import logging
from http.cookies import CookieError, SimpleCookie

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, WebSocket

from artek_buddy.auth import host_token_match
from artek_buddy.bus import EventHub
from artek_buddy.computer.service import (
    ComputerBusy,
    ComputerError,
    ComputerService,
    ComputerUnavailable,
)
from artek_buddy.config import Settings
from artek_buddy.consent import ConsentHub
from artek_buddy.contracts import (
    Bot,
    ThreadMessagePage,
    ThreadSnapshot,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import (
    DEFAULT_PAGE_SIZE,
)
from artek_buddy.runtime import (
    AgentRuntime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")


MAX_INBOX = 20


def current_app() -> FastAPI:
    from artek_buddy.main import app

    return app


def runtime() -> AgentRuntime:
    return current_app().state.runtime


def settings() -> Settings:
    return current_app().state.settings


def store() -> HistoryStore:
    return current_app().state.store


def hub() -> EventHub:
    return current_app().state.hub


def computers() -> ComputerService:
    return current_app().state.computers


def consent() -> ConsentHub:
    hub = getattr(current_app().state, "consent", None)
    if hub is None:
        raise HTTPException(status_code=503, detail="consent is not available")
    return hub


COOKIE_NAME = "artek_device"


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return token or None


def _cookie_named(header: str | None, name: str) -> str | None:
    if not header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(header)
    except CookieError:
        return None
    morsel = jar.get(name)
    if morsel is None:
        return None
    value = (morsel.value or "").strip()
    return value or None


def _actor_token(
    authorization: str | None,
    device_cookie: str | None,
    host_secret: str,
) -> tuple[str | None, str | None]:
    token = _bearer(authorization)
    if token is not None and host_token_match(token, host_secret):
        return ("host", None)
    cookie = (device_cookie or "").strip() or None
    if cookie and host_token_match(cookie, host_secret):
        cookie = None
    token = token or cookie
    if token is None:
        return (None, None)
    return ("device", token)


async def require_auth(
    authorization: str | None = Header(default=None),
    device_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    cfg: Settings = Depends(settings),
    history: HistoryStore = Depends(store),
) -> str:
    kind, token = _actor_token(authorization, device_cookie, cfg.agent_http_token)
    if kind == "host":
        return "host"
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        device = history.lookup_device_token(token)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if device is None:
        raise HTTPException(status_code=403, detail="invalid token")
    return device.id


async def require_host(
    authorization: str | None = Header(default=None),
    cfg: Settings = Depends(settings),
) -> None:
    token = _bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not host_token_match(token, cfg.agent_http_token):
        raise HTTPException(status_code=403, detail="host token required")


async def _authorize_websocket(websocket: WebSocket) -> str:
    cfg: Settings = websocket.app.state.settings
    history: HistoryStore = websocket.app.state.store
    cookie = _cookie_named(websocket.headers.get("cookie"), COOKIE_NAME)
    kind, token = _actor_token(
        websocket.headers.get("authorization"),
        cookie,
        cfg.agent_http_token,
    )
    if kind == "host":
        return "host"
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        device = history.lookup_device_token(token)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if device is None:
        raise HTTPException(status_code=403, detail="invalid token")
    return device.id


def _db_error(err: DatabaseUnavailable) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"message": str(err), "retryable": True},
    )


def _require_bot(history: HistoryStore, bot_id: str) -> Bot:
    bot = history.get_bot(bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="bot not found")
    return bot


def _resolve_bot(
    history: HistoryStore,
    rt: AgentRuntime,
    bot_id: str | None = None,
    session_id: str | None = None,
) -> Bot:
    if bot_id:
        return _require_bot(history, bot_id)
    if session_id:
        found = history.get_bot_by_agent(session_id)
        if found is not None:
            return found
    bot = history.default_bot(rt.default_agent_id)
    if bot is None:
        raise HTTPException(status_code=503, detail={"message": "no bot seeded", "retryable": True})
    return bot


def _page_for_bot(
    history: HistoryStore,
    bot: Bot,
    before: int | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> ThreadMessagePage:
    return history.page_messages(bot.thread_id, before=before, limit=limit)


def _snapshot(history: HistoryStore, bot: Bot) -> ThreadSnapshot:
    page = _page_for_bot(history, bot)
    service = getattr(current_app().state, "computers", None)
    if service is not None:
        status = service.status(bot)
    else:
        record = history.get_computer_for_bot(bot)
        status = record.status_for(bot.id, bot.computer_mode, history.busy_bot_name(record, bot.id))
    run = history.latest_run(bot.id)
    pending = None
    pending_ids: list[str] = []
    run_status = getattr(getattr(run, "status", None), "value", None) or getattr(
        run, "status", None
    )
    if run is not None and run_status == "waiting_input":
        pending_ids = history.pending_auto_consent_ids(bot.id, run.id)
        pending = pending_ids[-1] if pending_ids else None
    return ThreadSnapshot(
        bot_id=bot.id,
        thread_id=bot.thread_id,
        cursor=history.latest_seq(bot.thread_id),
        messages=page.messages,
        older_cursor=page.older_cursor,
        run=run,
        computer=status,
        subagents=sorted(history.list_subagents(bot.id), key=lambda item: item.index),
        pending_auto_consent_id=pending,
        pending_auto_consent_ids=pending_ids,
    )


def _computer_http(err: Exception) -> HTTPException:
    if isinstance(err, ComputerBusy):
        return HTTPException(status_code=409, detail=f"{err.name} is using the computer")
    if isinstance(err, ComputerUnavailable):
        return HTTPException(status_code=502, detail=str(err) or "screen unavailable")
    if isinstance(err, ComputerError):
        return HTTPException(status_code=400, detail=str(err))
    return HTTPException(status_code=500, detail=str(err))
