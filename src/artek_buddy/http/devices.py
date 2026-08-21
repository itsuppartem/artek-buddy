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

@router.post("/v1/devices/pairing", dependencies=[Depends(require_host)])
async def create_pairing(history: HistoryStore = Depends(store)) -> PairingCode:
    try:
        return history.create_pairing_code()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/devices")
async def create_device(
    request: Request,
    body: CreateDeviceInput,
    authorization: str | None = Header(default=None),
    cfg: Settings = Depends(settings),
    history: HistoryStore = Depends(store),
) -> DeviceCreated:
    pairing = (body.pairing_code or "").strip()
    token = _bearer(authorization)
    if pairing:
        key = request.client.host if request.client else "unknown"
        if not pairing_attempts.allow(key):
            raise HTTPException(
                status_code=429,
                detail="too many pairing attempts, try again in a few minutes",
            )
        try:
            ok = history.consume_pairing_code(pairing)
        except DatabaseUnavailable as err:
            raise _db_error(err) from err
        if not ok:
            pairing_attempts.record(key)
            raise HTTPException(status_code=403, detail="invalid or expired pairing code")
    elif token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    elif not host_token_match(token, cfg.agent_http_token):
        raise HTTPException(status_code=403, detail="host token or pairing code required")
    try:
        created = history.create_device(body.name, body.platform)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    log.info("device created id=%s", created.id)
    return created


@router.get("/v1/devices", dependencies=[Depends(require_auth)])
async def list_devices(history: HistoryStore = Depends(store)) -> DeviceList:
    try:
        return DeviceList(devices=history.list_devices())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.delete("/v1/devices/{device_id}")
async def revoke_device(
    device_id: str,
    actor: str = Depends(require_auth),
    history: HistoryStore = Depends(store),
) -> Device:
    if actor != "host" and actor != device_id:
        raise HTTPException(status_code=403, detail="cannot revoke another device")
    try:
        device = history.revoke_device(device_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device

