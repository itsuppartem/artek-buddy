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

@router.get("/v1/bots", dependencies=[Depends(require_auth)])
async def list_bots(history: HistoryStore = Depends(store)) -> BotList:
    try:
        return BotList(bots=history.list_bots())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/bots/archived", dependencies=[Depends(require_auth)])
async def list_archived_bots(history: HistoryStore = Depends(store)) -> BotList:
    try:
        return BotList(bots=history.list_archived_bots())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/bots/{bot_id}", dependencies=[Depends(require_auth)])
async def get_bot(bot_id: str, history: HistoryStore = Depends(store)) -> Bot:
    try:
        return _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots", dependencies=[Depends(require_auth)])
async def create_bot(
    body: CreateBotInput,
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> Bot:
    agent_id = await rt.create_session(name=body.name, persist_default=True)
    try:
        bot = history.create_bot(
            name=body.name,
            title=body.title,
            description=body.description,
            instructions=body.instructions,
            color=body.color,
            notify_on_finish=body.notify_on_finish,
            computer_mode=body.computer_mode,
            cursor_agent_id=agent_id,
        )
        rt.bind_agent_bot(agent_id, bot.id)
        return bot
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/duplicate", dependencies=[Depends(require_auth)])
async def duplicate_bot(
    bot_id: str,
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> Bot:
    try:
        original = _require_bot(history, bot_id)
        agent_id = await rt.create_session(name=f"{original.name} (Copy)", persist_default=False)
        duplicated = history.duplicate_bot(bot_id)
        attached = history.attach_agent(duplicated.id, agent_id)
        rt.bind_agent_bot(agent_id, attached.id)
        return attached
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.patch("/v1/bots/{bot_id}", dependencies=[Depends(require_auth)])
async def update_bot(
    bot_id: str,
    body: UpdateBotInput,
    history: HistoryStore = Depends(store),
) -> Bot:
    try:
        _require_bot(history, bot_id)
        updated = history.update_bot(
            bot_id,
            name=body.name,
            title=body.title,
            description=body.description,
            instructions=body.instructions,
            color=body.color,
            pinned=body.pinned,
            notify_on_finish=body.notify_on_finish,
            unread=body.unread,
            computer_mode=body.computer_mode,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="bot not found")
        return updated
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/bots/{bot_id}/subagents", dependencies=[Depends(require_auth)])
async def list_subagents(bot_id: str, history: HistoryStore = Depends(store)) -> SubagentList:
    try:
        bot = _require_bot(history, bot_id)
        return SubagentList(subagents=history.list_subagents(bot.id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/subagents/{subagent_id}/stop", dependencies=[Depends(require_auth)])
async def stop_subagent(
    bot_id: str,
    subagent_id: str,
    history: HistoryStore = Depends(store),
) -> Subagent:
    try:
        bot = _require_bot(history, bot_id)
        service = getattr(current_app().state, "subagents", None)
        if service is None:
            raise HTTPException(status_code=503, detail="subagents unavailable")
        return service.stop(bot, subagent_id)
    except SubagentError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/subagents/{subagent_id}/restart", dependencies=[Depends(require_auth)])
async def restart_subagent(
    bot_id: str,
    subagent_id: str,
    history: HistoryStore = Depends(store),
) -> Subagent:
    try:
        bot = _require_bot(history, bot_id)
        service = getattr(current_app().state, "subagents", None)
        if service is None:
            raise HTTPException(status_code=503, detail="subagents unavailable")
        return service.restart(bot, subagent_id)
    except SubagentError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/subagents/{subagent_id}/steer", dependencies=[Depends(require_auth)])
async def steer_subagent(
    bot_id: str,
    subagent_id: str,
    body: SteerSubagentInput,
    history: HistoryStore = Depends(store),
) -> Subagent:
    try:
        bot = _require_bot(history, bot_id)
        service = getattr(current_app().state, "subagents", None)
        if service is None:
            raise HTTPException(status_code=503, detail="subagents unavailable")
        return service.steer(bot, subagent_id, body.text)
    except SubagentError as err:
        if str(err) == "subagent not found":
            raise HTTPException(status_code=404, detail=str(err)) from err
        raise HTTPException(status_code=409, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/computer", dependencies=[Depends(require_auth)])
async def set_bot_computer(
    bot_id: str,
    body: SetComputerInput,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> Bot:
    try:
        bot = _require_bot(history, bot_id)
        return boxes.switch_mode(bot, body.mode)
    except ComputerBusy as err:
        raise _computer_http(err) from err
    except ComputerError as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/archive", dependencies=[Depends(require_auth)])
async def archive_bot(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        _require_bot(history, bot_id)
        history.archive_bot(bot_id)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/bots/{bot_id}/restore", dependencies=[Depends(require_auth)])
async def restore_bot(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        restored = history.restore_bot(bot_id)
        if restored is None:
            raise HTTPException(status_code=404, detail="bot not found")
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.delete("/v1/bots/{bot_id}", dependencies=[Depends(require_auth)])
async def remove_bot(
    bot_id: str,
    delete_memories: bool = Query(default=False),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> OkResponse:
    try:
        bot = history.get_bot(bot_id)
        if bot is None:
            raise HTTPException(status_code=404, detail="bot not found")
        _cancel_turns(bot.id)
        service = getattr(current_app().state, "subagents", None)
        if service is not None:
            try:
                service.stop_all(bot)
            except Exception:
                log.exception("failed to stop subagents while deleting bot %s", bot.id)
        try:
            boxes.remove_bot_uploads(bot)
        except Exception:
            log.exception("failed to remove inbox copies while deleting bot %s", bot.id)
        try:
            boxes.release_for_deleted_bot(bot)
        except Exception:
            log.exception("failed to release computer while deleting bot %s", bot.id)
        deleted = history.delete_bot(bot_id, delete_memories=delete_memories)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if not deleted:
        raise HTTPException(status_code=404, detail="bot not found")
    shutil.rmtree(Path(current_app().state.settings.agent_data_dir) / "artifacts" / bot_id, ignore_errors=True)
    return OkResponse(ok=True)

