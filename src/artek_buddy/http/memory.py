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

from fastapi import APIRouter

from artek_buddy.http.deps import (
    computers,
    consent,
    current_app,
    hub,
    require_auth,
    require_host,
    runtime,
    settings,
    store,
    _authorize_websocket,
    _bearer,
    _computer_http,
    _db_error,
    _page_for_bot,
    _require_bot,
    _resolve_bot,
    _snapshot,
)
from artek_buddy.http.turns import (
    _accept_turn,
    _cancel_turns,
    _emit,
    _emit_computer,
    _ingest_thread_files,
    _resume_parked_takeover,
)

router = APIRouter()

@router.get("/v1/memory", dependencies=[Depends(require_auth)])
async def list_memory(
    bot_id: str | None = Query(default=None),
    scope: MemoryScope | None = Query(default=None),
    history: HistoryStore = Depends(store),
) -> MemoryDocumentList:
    try:
        if bot_id:
            _require_bot(history, bot_id)
        return MemoryDocumentList(documents=history.list_memory(bot_id=bot_id, scope=scope))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/memory", dependencies=[Depends(require_auth)])
async def create_memory(
    body: CreateMemoryInput,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> MemoryDocument:
    try:
        if body.scope == MemoryScope.bot:
            if not body.bot_id:
                raise HTTPException(status_code=400, detail="bot memory needs a bot")
            bot = _require_bot(history, body.bot_id)
        else:
            bot = None
        document = history.create_memory(
            body.scope,
            body.content,
            bot_id=body.bot_id,
            path=body.path,
        )
        hub = _memory_hub()
        if hub is not None:
            try:
                hub.index_document(document, kind=body.kind or "preference", source="panel")
            except Exception:
                log.exception("failed to index panel memory")
    except MemoryPathError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except MemoryConflict as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if bot is not None:
        _emit(
            events,
            bot,
            ProductEventType.MEMORY_REVISED,
            {
                "document_id": document.id,
                "path": document.path,
                "scope": document.scope.value if hasattr(document.scope, "value") else document.scope,
                "revision": document.revision,
            },
        )
    return document


@router.get("/v1/memory/export", dependencies=[Depends(require_auth)])
async def export_memory(
    bot_id: str | None = Query(default=None),
    history: HistoryStore = Depends(store),
) -> MarkdownExport:
    try:
        if bot_id:
            _require_bot(history, bot_id)
        documents = history.list_memory(bot_id=bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return MarkdownExport(markdown=export_markdown(documents))


@router.patch("/v1/memory/{document_id}", dependencies=[Depends(require_auth)])
async def update_memory(
    document_id: str,
    body: MemoryUpdateInput,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> MemoryDocument:
    try:
        document = history.update_memory(document_id, body.content)
        hub = _memory_hub()
        if hub is not None and document is not None:
            try:
                hub.index_document(document, source="panel")
            except Exception:
                log.exception("failed to index panel memory")
    except MemoryPathError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if document is None:
        raise HTTPException(status_code=404, detail="memory document not found")
    if document.bot_id:
        try:
            bot = history.get_bot(document.bot_id)
        except DatabaseUnavailable as err:
            raise _db_error(err) from err
        if bot is not None:
            _emit(
                events,
                bot,
                ProductEventType.MEMORY_REVISED,
                {
                    "document_id": document.id,
                    "path": document.path,
                    "scope": document.scope.value if hasattr(document.scope, "value") else document.scope,
                    "revision": document.revision,
                },
            )
    return document


@router.delete("/v1/memory/{document_id}", dependencies=[Depends(require_auth)])
async def remove_memory(
    document_id: str,
    history: HistoryStore = Depends(store),
) -> OkResponse:
    try:
        hub = _memory_hub()
        deleted = hub.remove_document(document_id) if hub is not None else history.delete_memory(document_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if not deleted:
        raise HTTPException(status_code=404, detail="memory document not found")
    return OkResponse(ok=True)

