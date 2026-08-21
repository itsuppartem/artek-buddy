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

@router.get("/v1/threads/{bot_id}", dependencies=[Depends(require_auth)])
async def get_thread(bot_id: str, history: HistoryStore = Depends(store)) -> ThreadSnapshot:
    try:
        bot = _require_bot(history, bot_id)
        return _snapshot(history, bot)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/threads/{bot_id}/messages", dependencies=[Depends(require_auth)])
async def thread_messages(
    bot_id: str,
    before: int | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE),
    history: HistoryStore = Depends(store),
) -> ThreadMessagePage:
    try:
        bot = _require_bot(history, bot_id)
        return _page_for_bot(history, bot, before=before, limit=limit)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/threads/{bot_id}/messages")
async def send_thread_message(
    bot_id: str,
    body: ThreadSendInput,
    actor: str = Depends(require_auth),
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> ThreadSendResult:
    rt.set_turn_device(actor)
    try:
        bot = _require_bot(history, bot_id)
        hosted = _ingest_thread_files(
            history,
            rt,
            bot,
            list(body.attachments),
            list(body.attachment_ids),
            copy_to_inbox=True,
        ) if (body.attachments or body.attachment_ids) else []
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return await _accept_turn(
        history,
        rt,
        events,
        bot,
        body.text,
        trigger=body.trigger,
        reply_to_id=body.reply_to_id,
        attachments=hosted,
    )


@router.post("/v1/threads/{bot_id}/attachments", dependencies=[Depends(require_auth)])
async def upload_thread_attachments(
    bot_id: str,
    body: AttachmentUploadInput,
    history: HistoryStore = Depends(store),
    rt: AgentRuntime = Depends(runtime),
) -> AttachmentList:
    try:
        bot = _require_bot(history, bot_id)
        hosted = _ingest_thread_files(history, rt, bot, list(body.files), [], copy_to_inbox=False)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return AttachmentList(
        attachments=[
            HostedAttachment(
                id=item["id"],
                name=item["name"],
                mime_type=item["mime_type"],
                size=item["size"],
                path=item["path"],
            )
            for item in hosted
        ]
    )


@router.get("/v1/artifacts", dependencies=[Depends(require_auth)])
async def list_artifacts(
    bot_id: str = Query(...),
    history: HistoryStore = Depends(store),
) -> ArtifactList:
    try:
        _require_bot(history, bot_id)
        return ArtifactList(artifacts=history.list_artifacts(bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/artifacts/{artifact_id}", dependencies=[Depends(require_auth)])
async def download_artifact(
    artifact_id: str,
    history: HistoryStore = Depends(store),
) -> FileResponse:
    try:
        found = history.get_artifact(artifact_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if found is None:
        raise HTTPException(status_code=404, detail="file not found")
    artifact, stored = found
    root = (Path(current_app().state.settings.agent_data_dir) / "artifacts").resolve()
    path = Path(stored).resolve()
    try:
        path.relative_to(root)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="file not found") from err
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, filename=artifact.name, media_type=artifact.mime_type)


@router.post("/v1/threads/{bot_id}/stop", dependencies=[Depends(require_auth)])
async def stop_thread(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> OkResponse:
    try:
        bot = _require_bot(history, bot_id)
        _cancel_turns(bot_id)
        service = getattr(current_app().state, "subagents", None)
        if service is not None:
            service.stop_all(bot)
        cancelled_ids = history.cancel_active_runs(bot_id)
        for run_id in cancelled_ids:
            _emit(
                events,
                bot,
                ProductEventType.RUN_CANCELLED,
                {"run_id": run_id, "status": "cancelled"},
                run_id=run_id,
            )
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return OkResponse(ok=True)


@router.post("/v1/threads/{bot_id}/follow-up")
async def follow_up_thread_message(
    bot_id: str,
    body: ThreadFollowUpInput,
    actor: str = Depends(require_auth),
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> OkResponse:
    rt.set_turn_device(actor)
    try:
        bot = _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    await _accept_turn(history, rt, events, bot, body.text, trigger="follow_up")
    return OkResponse(ok=True)


@router.post("/v1/threads/{bot_id}/read", dependencies=[Depends(require_auth)])
async def mark_thread_read(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        _require_bot(history, bot_id)
        history.set_bot_unread(bot_id, False)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/threads/{bot_id}/unread", dependencies=[Depends(require_auth)])
async def mark_thread_unread(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        _require_bot(history, bot_id)
        history.set_bot_unread(bot_id, True)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/events", dependencies=[Depends(require_auth)])
async def subscribe_workspace_events(
    events: EventHub = Depends(hub),
) -> StreamingResponse:
    async def gen():
        async for item in events.subscribe_workspace():
            if item is HEARTBEAT:
                yield ": keepalive\n\n"
                continue
            data = item.model_dump_json()
            yield f"id: {item.id}\nevent: {item.type.value}\ndata: {data}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/v1/threads/{bot_id}/events", dependencies=[Depends(require_auth)])
async def subscribe_thread_events(
    bot_id: str,
    after: str | None = Query(default=None),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> StreamingResponse:
    try:
        bot = _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err

    async def gen():
        async for item in events.subscribe(bot_id, after=after):
            if item is HEARTBEAT:
                yield ": keepalive\n\n"
                continue
            if item is REPLAY_GAP:
                gap = ProductEvent(
                    id=new_id("evt"),
                    workspace_id=bot.workspace_id,
                    thread_id=bot.thread_id,
                    bot_id=bot.id,
                    seq=0,
                    type=ProductEventType.THREAD_REPLAY_GAP,
                    created_at=isoformat_utc(),
                    payload={"after": after},
                )
                data = gap.model_dump_json()
                yield f"id: {gap.id}\nevent: {gap.type.value}\ndata: {data}\n\n"
                continue
            data = item.model_dump_json()
            yield f"id: {item.id}\nevent: {item.type.value}\ndata: {data}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/v1/messages", dependencies=[Depends(require_auth)])
async def list_messages(
    bot_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    before: int | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE),
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
) -> ThreadMessagePage:
    try:
        bot = _resolve_bot(history, rt, bot_id=bot_id, session_id=session_id)
        return _page_for_bot(history, bot, before=before, limit=limit)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/runs")
async def create_run(
    body: RunRequest,
    actor: str = Depends(require_auth),
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> Run:
    rt.set_turn_device(actor)
    try:
        bot = _resolve_bot(history, rt, bot_id=body.bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    result = await _accept_turn(history, rt, events, bot, body.text)
    if result.run is None:
        raise HTTPException(status_code=500, detail="run missing after send")
    return result.run

