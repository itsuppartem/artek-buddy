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

@router.get("/v1/consents/{consent_id}")
async def get_consent(
    consent_id: str,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> ConsentJob:
    job = hub.get_job(consent_id)
    if job is None:
        raise HTTPException(status_code=404, detail="consent not found")
    return ConsentJob.model_validate(job)


@router.post("/v1/consents/{consent_id}")
async def answer_consent(
    consent_id: str,
    body: ConsentAnswerInput,
    actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    row = hub.answer(consent_id, body.decision, None if actor == "host" else actor)
    if row is None:
        if hub.get_job(consent_id) is None:
            raise HTTPException(status_code=404, detail="consent not found")
        raise HTTPException(status_code=400, detail="consent not pending")
    return OkResponse(ok=True)


@router.post("/v1/consents/{consent_id}/file")
async def upload_consent_file(
    consent_id: str,
    body: ConsentFileInput,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    data = b""
    if body.content_base64:
        try:
            data = base64.b64decode(body.content_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid content_base64") from exc
    elif body.text is not None:
        data = body.text.encode()
    else:
        raise HTTPException(status_code=400, detail="text or content_base64 required")
    if len(data) > 1_000_000:
        raise HTTPException(status_code=400, detail="file is larger than 1 MB")
    if not hub.put_owner_file(consent_id, body.name, data):
        raise HTTPException(status_code=404, detail="consent not found")
    hub.put_owner_result(
        consent_id,
        {"ok": True, "name": body.name, "bytes": len(data), "_data": data, "content_base64": body.content_base64, "text": body.text},
    )
    return OkResponse(ok=True)


@router.post("/v1/consents/{consent_id}/result")
async def upload_consent_result(
    consent_id: str,
    body: ConsentResultInput,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    payload = body.model_dump(exclude_none=True)
    if body.content_base64:
        try:
            payload["_data"] = base64.b64decode(body.content_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid content_base64") from exc
    elif body.text is not None and "_data" not in payload:
        payload["_data"] = body.text.encode()
    if not hub.put_owner_result(consent_id, payload):
        raise HTTPException(status_code=404, detail="consent not found")
    return OkResponse(ok=True)

