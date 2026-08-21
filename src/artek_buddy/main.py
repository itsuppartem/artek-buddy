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


from artek_buddy.http.bots import router as bots_router
from artek_buddy.http.computer import router as computer_router
from artek_buddy.http.consents import router as consents_router
from artek_buddy.http.devices import router as devices_router
from artek_buddy.http.memory import router as memory_router
from artek_buddy.http.routines import router as routines_router
from artek_buddy.http.session import router as session_router
from artek_buddy.http.threads import router as threads_router
from artek_buddy.http.turns import _handle_takeover_request, _kick_inbox, _shutdown_work

class _RedactNovncFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/novnc/" not in message:
            return True
        record.msg = re.sub(r"/novnc/\S+", "/novnc/[redacted]", message)
        record.args = ()
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactNovncFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = HistoryStore(settings.database_url)
    try:
        store.open()
        store.apply_migrations()
        log.info("postgres ready")
    except DatabaseUnavailable:
        log.exception("postgres unavailable at boot; history routes will return 503")

    computers = ComputerService(store, settings)
    try:
        async with open_runtime(settings, store, computers) as runtime:
            try:
                store.ensure_workspace()
                leftover = store.fail_orphaned_runs()
                if leftover:
                    log.warning("marked %s leftover run(s) failed after restart", leftover)
                reaped = computers.reap_orphan_computers()
                if reaped:
                    log.warning("destroyed %s computer(s) with no remaining bot", reaped)
            except DatabaseUnavailable:
                log.exception("workspace setup skipped; postgres unavailable")
            app.state.settings = settings
            app.state.runtime = runtime
            app.state.store = store
            app.state.computers = computers
            app.state.hub = EventHub()
            app.state.active_turns = {}
            memory = MemoryHub(store, GatewayClient(settings.memory_gateway_url))
            runtime.memory = memory
            app.state.memory = memory
            consent = ConsentHub(store, app.state.hub, settings)
            runtime.consent = consent
            app.state.consent = consent
            subagents = SubagentService(store, runtime)
            subagents.bind(app.state.hub, asyncio.get_running_loop())
            runtime.subagents = subagents
            runtime.events = app.state.hub
            runtime.loop = asyncio.get_running_loop()
            app.state.subagents = subagents
            runtime.on_takeover_requested = _handle_takeover_request
            try:
                for bot in store.list_bots():
                    asyncio.create_task(
                        _kick_inbox(store, runtime, app.state.hub, bot),
                        name=f"inbox-recover-{bot.id}",
                    )
            except DatabaseUnavailable:
                log.exception("inbox recovery skipped; postgres unavailable")
            log.info(
                "listening on %s:%s runtime=%s default_agent=%s",
                settings.http_host,
                settings.http_port,
                runtime_kind(settings),
                runtime.default_agent_id,
            )
            yield
            await _shutdown_work()
    finally:
        store.close()



app = FastAPI(
    title="Artek Buddy",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(devices_router)
app.include_router(session_router)
app.include_router(bots_router)
app.include_router(threads_router)
app.include_router(consents_router)
app.include_router(memory_router)
app.include_router(routines_router)
app.include_router(computer_router)


@app.get("/health")
async def health() -> HealthResponse:
    current = getattr(app.state, "runtime", None)
    history = getattr(app.state, "store", None)
    db_ok = False
    if history is not None:
        try:
            db_ok = history.available()
        except Exception:
            db_ok = False
    return HealthResponse(
        ok=current is not None,
        db=db_ok,
    )

