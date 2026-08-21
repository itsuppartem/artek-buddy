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

@router.get("/v1/routines", dependencies=[Depends(require_auth)])
async def list_routines(
    bot_id: str = Query(...),
    history: HistoryStore = Depends(store),
) -> RoutineList:
    try:
        _require_bot(history, bot_id)
        return RoutineList(routines=history.list_routines(bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/routines", dependencies=[Depends(require_auth)])
async def create_routine(
    body: CreateRoutineInput,
    history: HistoryStore = Depends(store),
) -> Routine:
    try:
        _require_bot(history, body.bot_id)
        return history.create_routine(
            body.bot_id,
            body.name,
            body.prompt,
            body.cron,
            body.timezone,
            body.notify,
            body.active,
        )
    except CronError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.patch("/v1/routines/{routine_id}", dependencies=[Depends(require_auth)])
async def update_routine(
    routine_id: str,
    body: UpdateRoutineInput,
    history: HistoryStore = Depends(store),
) -> Routine:
    try:
        routine = history.update_routine(
            routine_id,
            name=body.name,
            prompt=body.prompt,
            cron=body.cron,
            timezone_name=body.timezone,
            notify=body.notify,
            active=body.active,
        )
    except CronError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if routine is None:
        raise HTTPException(status_code=404, detail="routine not found")
    return routine


@router.delete("/v1/routines/{routine_id}", dependencies=[Depends(require_auth)])
async def remove_routine(
    routine_id: str,
    history: HistoryStore = Depends(store),
) -> OkResponse:
    try:
        deleted = history.delete_routine(routine_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if not deleted:
        raise HTTPException(status_code=404, detail="routine not found")
    return OkResponse(ok=True)


@router.post("/v1/routines/{routine_id}/test")
async def test_routine(
    routine_id: str,
    actor: str = Depends(require_auth),
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> TestRunResult:
    rt.set_turn_device(actor)
    try:
        routine = history.get_routine(routine_id)
        if routine is None:
            raise HTTPException(status_code=404, detail="routine not found")
        bot = _require_bot(history, routine.bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    result = await _accept_turn(history, rt, events, bot, routine.prompt, trigger="routine")
    return TestRunResult(
        routine_id=routine.id,
        task_id=result.task_id,
        run_id=result.run_id,
        seq=result.seq,
    )

