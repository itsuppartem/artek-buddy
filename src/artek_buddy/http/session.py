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

@router.get("/v1/models", dependencies=[Depends(require_auth)])
async def list_models(rt: AgentRuntime = Depends(runtime)) -> dict[str, Any]:
    return {"models": await rt.list_models()}


@router.get("/v1/session", dependencies=[Depends(require_auth)])
async def get_session(
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> SessionResponse:
    try:
        bot = history.default_bot(rt.default_agent_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return SessionResponse(
        agent_id=rt.default_agent_id or "",
        bot_id=bot.id if bot else None,
        thread_id=bot.thread_id if bot else None,
    )


@router.post("/v1/session", dependencies=[Depends(require_auth)])
async def create_session(
    body: SessionRequest,
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> SessionResponse:
    agent_id = await rt.create_session(name=body.name, persist_default=True)
    try:
        bot = history.create_bot(name=body.name or DEFAULT_BOT_NAME, cursor_agent_id=agent_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return SessionResponse(agent_id=agent_id, bot_id=bot.id, thread_id=bot.thread_id)


@router.get("/v1/me", dependencies=[Depends(require_auth)])
async def get_me() -> Me:
    return Me()


@router.get("/v1/deployment", dependencies=[Depends(require_auth)])
async def get_deployment() -> DeploymentSettings:
    return DeploymentSettings()


@router.patch("/v1/deployment", dependencies=[Depends(require_auth)])
async def update_deployment(body: UpdateDeploymentInput) -> DeploymentSettings:
    return DeploymentSettings(
        signups_enabled=body.signups_enabled if body.signups_enabled is not None else True,
        signup_allowlist=body.signup_allowlist if body.signup_allowlist is not None else [],
        computer_host=body.computer_host if body.computer_host is not None else "docker",
    )

