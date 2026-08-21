from __future__ import annotations

import asyncio
import base64
import logging
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import FileResponse, Response, StreamingResponse

from artek_buddy.auth import host_token_match, pairing_attempts
from artek_buddy.bus import HEARTBEAT, REPLAY_GAP, EventHub
from artek_buddy.config import Settings, get_settings
from artek_buddy.contracts import (
    ArtifactList,
    AttachmentList,
    AttachmentUploadInput,
    HostedAttachment,
    Bot,
    BotIdInput,
    BotList,
    ComputerFileContent,
    ComputerFileList,
    ComputerInput,
    ComputerStatus,
    CreateBotInput,
    CreateDeviceInput,
    CreateMemoryInput,
    CreateRoutineInput,
    DeleteBotInput,
    DeploymentSettings,
    Device,
    DeviceCreated,
    DeviceList,
    HealthResponse,
    MarkdownExport,
    Me,
    MemoryDocument,
    MemoryDocumentList,
    MemoryScope,
    MemoryUpdateInput,
    OkResponse,
    PairingCode,
    ProductEvent,
    ProductEventType,
    Routine,
    RoutineList,
    Run,
    ScreenUrlResult,
    RunRequest,
    SessionRequest,
    SessionResponse,
    SetComputerInput,
    SteerSubagentInput,
    Subagent,
    SubagentList,
    TakeoverResult,
    TestRunResult,
    ThreadFollowUpInput,
    ThreadMessage,
    ThreadMessagePage,
    ConsentAnswerInput,
    ConsentFileInput,
    ConsentJob,
    ConsentResultInput,
    ThreadSendInput,
    ThreadSendResult,
    ThreadSnapshot,
    UpdateBotInput,
    UpdateDeploymentInput,
    UpdateRoutineInput,
)
from artek_buddy.cron import CronError
from artek_buddy.computer.proxy import proxy_novnc_http, proxy_novnc_ws
from artek_buddy.computer.service import ComputerBusy, ComputerError, ComputerService, ComputerUnavailable
from artek_buddy.db import DatabaseUnavailable, product_run_status
from artek_buddy.db.history import HistoryStore, InboxFullError
from artek_buddy.db.shaping import (
    DEFAULT_BOT_NAME,
    DEFAULT_PAGE_SIZE,
    blocks_text,
    isoformat_utc,
    new_id,
    preview_snippet,
)
from artek_buddy.consent import ConsentHub
from artek_buddy.memory import (
    MemoryConflict,
    MemoryPathError,
    compact_thread_context,
    export_markdown,
    format_memory_context,
    format_subagent_context,
    wrap_turn_prompt,
)
from artek_buddy.uploads import (
    UploadError,
    format_user_turn,
    ingest_uploads,
    preview_for_upload,
    user_file_blocks,
)
from artek_buddy.memory_gateway import GatewayClient
from artek_buddy.memory_hub import MemoryHub, should_persist_ask
from artek_buddy.subagents import SubagentError, SubagentService
from artek_buddy.runtime import (
    AgentRuntime,
    AgentRuntimeError,
    ProductStreamEvent,
    RunRecord,
    open_runtime,
    runtime_kind,
)
from artek_buddy.stream import accumulate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")

from fastapi import FastAPI

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


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return token or None


async def require_auth(
    authorization: str | None = Header(default=None),
    cfg: Settings = Depends(settings),
    history: HistoryStore = Depends(store),
) -> str:
    token = _bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if host_token_match(token, cfg.agent_http_token):
        return "host"
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
    token = _bearer(websocket.headers.get("authorization"))
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if host_token_match(token, cfg.agent_http_token):
        return "host"
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
    run_status = getattr(getattr(run, "status", None), "value", None) or getattr(run, "status", None)
    if run is not None and run_status == "waiting_input":
        pending = history.pending_auto_consent_id(bot.id, run.id)
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
    )


def _computer_http(err: Exception) -> HTTPException:
    if isinstance(err, ComputerBusy):
        return HTTPException(status_code=409, detail=f"{err.name} is using the computer")
    if isinstance(err, ComputerUnavailable):
        return HTTPException(status_code=502, detail=str(err) or "screen unavailable")
    if isinstance(err, ComputerError):
        return HTTPException(status_code=400, detail=str(err))
    return HTTPException(status_code=500, detail=str(err))

