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


class _RedactNovncFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/novnc/" not in message:
            return True
        record.msg = re.sub(r"/novnc/\S+", "/novnc/[redacted]", message)
        record.args = ()
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactNovncFilter())

MAX_INBOX = 20


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


def runtime() -> AgentRuntime:
    return app.state.runtime


def settings() -> Settings:
    return app.state.settings


def store() -> HistoryStore:
    return app.state.store


def hub() -> EventHub:
    return app.state.hub


def computers() -> ComputerService:
    return app.state.computers


def consent() -> ConsentHub:
    hub = getattr(app.state, "consent", None)
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
    service = getattr(app.state, "computers", None)
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


def _emit_computer(events: EventHub, bot: Bot, status: ComputerStatus) -> None:
    payload = status.model_dump(mode="json")
    payload["status"] = status.state
    _emit(events, bot, ProductEventType.COMPUTER_STATUS, payload)


def _handle_takeover_request(bot_id: str, run_id: str | None) -> None:
    history: HistoryStore = app.state.store
    events: EventHub = app.state.hub
    service: ComputerService = app.state.computers
    bot = history.get_bot(bot_id)
    if bot is None:
        return
    try:
        service.release(bot)
        _emit(
            events,
            bot,
            ProductEventType.COMPUTER_TAKEOVER_REQUESTED,
            {"run_id": run_id},
            run_id=run_id,
        )
        _emit_computer(events, bot, service.status(bot))
    except Exception:
        log.exception("takeover request failed")
    _cancel_turns(bot_id, run_id)


async def _ensure_agent(history: HistoryStore, rt: AgentRuntime, bot: Bot) -> Bot:
    live_id = await rt.ensure_session(
        bot.cursor_agent_id,
        name=bot.name or DEFAULT_BOT_NAME,
        bot_id=bot.id,
    )
    rt.bind_agent_bot(live_id, bot.id)
    if bot.cursor_agent_id != live_id:
        return history.attach_agent(bot.id, live_id)
    return bot


def _emit(
    events: EventHub,
    bot: Bot,
    event_type: ProductEventType,
    payload: dict[str, Any],
    run_id: str | None = None,
) -> ProductEvent:
    event = ProductEvent(
        id=new_id("evt"),
        workspace_id=bot.workspace_id,
        thread_id=bot.thread_id,
        bot_id=bot.id,
        seq=events.next_seq(bot.id),
        type=event_type,
        created_at=isoformat_utc(),
        payload=payload,
        run_id=run_id,
    )
    events.publish(event)
    return event


def _emit_remembered(
    events: EventHub,
    bot: Bot,
    text: str,
    run_id: str | None,
) -> None:
    label = f"Remembered: {text}".strip() if text else "Remembered a note"
    _emit(events, bot, ProductEventType.THREAD_META, {"text": label[:160]}, run_id=run_id)


def _memory_hub(rt: AgentRuntime | None = None) -> MemoryHub | None:
    if rt is not None:
        found = getattr(rt, "memory", None)
        if found is not None:
            return found
    return getattr(app.state, "memory", None)


def _ask_question(message: ThreadMessage) -> str | None:
    for block in message.blocks or []:
        data = block.model_dump() if hasattr(block, "model_dump") else block
        if isinstance(data, dict) and data.get("kind") == "ask":
            question = str(data.get("text") or "").strip()
            return question or None
    return None


def _memory_context(history: HistoryStore, rt: AgentRuntime, bot: Bot, text: str) -> str | None:
    hub = _memory_hub(rt)
    if hub is not None:
        return hub.context_for_turn(bot.id, text)
    return format_memory_context(history.memory_for_agent(bot.id))


def _emit_answered_asks(
    history: HistoryStore,
    events: EventHub,
    bot: Bot,
    text: str,
    run_id: str | None,
) -> None:
    hub = _memory_hub()
    for message in history.answer_pending_asks(bot.thread_id, text):
        _emit(
            events,
            bot,
            ProductEventType.THREAD_MESSAGE_CREATED,
            {"message": message.model_dump(mode="json")},
            run_id=run_id,
        )
        if hub is None:
            continue
        question = _ask_question(message)
        if not should_persist_ask(question, text):
            continue
        try:
            entry = hub.capture(
                text,
                kind="choice",
                bot_id=bot.id,
                source="ask",
                run_id=run_id,
                thread_id=bot.thread_id,
                question=question,
            )
            if entry is not None:
                _emit_remembered(events, bot, entry.text, run_id)
        except Exception:
            log.exception("failed to capture ask answer in memory")


def _turn_bucket(bot_id: str) -> dict[str, asyncio.Task[Any]]:
    turns = getattr(app.state, "active_turns", None)
    if turns is None:
        return {}
    bucket = turns.get(bot_id)
    if bucket is None:
        bucket = {}
        turns[bot_id] = bucket
    return bucket


def _register_turn(bot_id: str, run_id: str, task: asyncio.Task[Any]) -> None:
    _turn_bucket(bot_id)[run_id] = task


def _drop_turn(bot_id: str, run_id: str) -> None:
    turns = getattr(app.state, "active_turns", None)
    if not turns:
        return
    bucket = turns.get(bot_id)
    if not bucket:
        return
    bucket.pop(run_id, None)
    if not bucket:
        turns.pop(bot_id, None)


def _cancel_turns(bot_id: str, run_id: str | None = None) -> None:
    turns = getattr(app.state, "active_turns", None)
    if not turns:
        return
    bucket = turns.get(bot_id) or {}
    if run_id:
        tasks = [bucket[run_id]] if run_id in bucket else []
    else:
        tasks = list(bucket.values())
        turns.pop(bot_id, None)
    for task in tasks:
        if task and not task.done():
            task.cancel()


async def _shutdown_work() -> None:
    pending: list[asyncio.Task[Any]] = []
    turns = getattr(app.state, "active_turns", None)
    if turns:
        for bucket in list(turns.values()):
            for task in list(bucket.values()):
                if task and not task.done():
                    task.cancel()
                    pending.append(task)
    service = getattr(app.state, "subagents", None)
    history = getattr(app.state, "store", None)
    if service is not None and history is not None:
        try:
            for bot in history.list_bots():
                service.stop_all(bot)
        except Exception:
            log.exception("failed to stop subagents during shutdown")
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _message_excerpt(message: ThreadMessage, limit: int = 400) -> str:
    raw: list[dict[str, Any]] = []
    for block in message.blocks or []:
        if hasattr(block, "model_dump"):
            raw.append(block.model_dump())
        elif isinstance(block, dict):
            raw.append(block)
    return preview_snippet(blocks_text(raw), limit)


def _ingest_thread_files(
    history: HistoryStore,
    rt: AgentRuntime,
    bot: Bot,
    files: list[Any] | None,
    existing_ids: list[str] | None,
    *,
    copy_to_inbox: bool,
) -> list[dict[str, Any]]:
    try:
        return ingest_uploads(
            store=history,
            home=Path(rt.home_cwd(bot.id)),
            data_dir=Path(rt.settings.agent_data_dir),
            bot_id=bot.id,
            files=files or [],
            existing_ids=existing_ids or [],
            copy_to_inbox=copy_to_inbox,
        )
    except UploadError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


async def _accept_turn(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
    text: str,
    trigger: str = "user",
    reply_to_id: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> ThreadSendResult:
    bot = await _ensure_agent(history, rt, bot)
    hosted = attachments or []
    display = (text or "").strip()
    prompt = format_user_turn(display, hosted) if hosted else display
    try:
        parked = history.waiting_takeover_run(bot.id)
        if parked is not None:
            _msg, finished = history.finish_turn(bot, parked, "", "cancelled", error="Stopped.")
            _emit(
                events,
                bot,
                ProductEventType.RUN_CANCELLED,
                {"run": finished.model_dump(mode="json"), "error": "Stopped."},
                run_id=finished.id,
            )
        reply_msg = None
        if reply_to_id:
            reply_msg = history.get_message_in_thread(bot.thread_id, reply_to_id)
            if reply_msg is None:
                raise HTTPException(status_code=400, detail="reply target not found")
        user_msg, run, queued = history.begin_or_enqueue_turn(
            bot,
            prompt,
            model_provider=runtime_kind(rt.settings),
            model_id=rt.settings.cursor_model,
            trigger=trigger,
            reply_to_id=reply_msg.id if reply_msg else None,
            max_inbox=MAX_INBOX,
            blocks=user_file_blocks(display, hosted) if hosted else None,
            preview=preview_for_upload(display, hosted) if hosted else None,
        )
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    except InboxFullError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err

    _emit_answered_asks(history, events, bot, display or prompt, run.id)
    _emit(
        events,
        bot,
        ProductEventType.THREAD_MESSAGE_CREATED,
        {"message": user_msg.model_dump(mode="json")},
        run_id=run.id,
    )
    if queued:
        return ThreadSendResult(
            task_id=run.task_id,
            run_id=run.id,
            seq=user_msg.seq,
            run=run,
            queued=True,
        )
    _emit(
        events,
        bot,
        ProductEventType.RUN_STARTED,
        {"run": run.model_dump(mode="json")},
        run_id=run.id,
    )
    inbox_items = history.drain_inbox(bot.id)
    task = asyncio.create_task(
        _run_turn(
            history,
            rt,
            events,
            bot,
            prompt,
            run,
            session_id=bot.cursor_agent_id,
            attach_agent=True,
            reply=reply_msg,
            inbox_items=inbox_items,
        ),
        name=f"turn-{run.id}",
    )
    _register_turn(bot.id, run.id, task)
    return ThreadSendResult(task_id=run.task_id, run_id=run.id, seq=user_msg.seq, run=run)


async def _run_turn(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
    text: str,
    run: Run,
    session_id: str | None = None,
    attach_agent: bool = True,
    reply: ThreadMessage | None = None,
    inbox_items: list[dict[str, str | None]] | None = None,
) -> None:
    agent_id = session_id or bot.cursor_agent_id
    rt.set_current_turn_context(bot.id, run.id, bot.thread_id, agent_id=agent_id, role="lead")
    draft = ""
    thinking = ""
    reply_text = ""
    error: str | None = None
    status = "failed"
    try:
        page = history.page_messages(bot.thread_id, limit=40)
        thread_context = compact_thread_context(page.messages)
        inbox_context = _format_inbox(history, bot, inbox_items) if inbox_items else None
        memory_prompt = wrap_turn_prompt(
            text,
            _memory_context(history, rt, bot, text),
            reply_excerpt=_message_excerpt(reply) if reply else None,
            reply_role=(
                (reply.role.value if hasattr(reply.role, "value") else str(reply.role))
                if reply is not None
                else None
            ),
            role="lead",
            subagent_context=format_subagent_context(history.list_subagents(bot.id)),
            thread_context=thread_context,
            inbox_context=inbox_context,
        )
        async for item in rt.stream(memory_prompt, session_id=agent_id, bot_id=bot.id):
            if isinstance(item, RunRecord):
                if attach_agent and item.agent_id and item.agent_id != bot.cursor_agent_id:
                    bot = history.attach_agent(bot.id, item.agent_id)
                    rt.bind_agent_bot(item.agent_id, bot.id)
                elif item.agent_id:
                    rt.bind_agent_bot(item.agent_id, bot.id)
                status = product_run_status(item.status)
                reply_text = item.result or draft or ""
                if status != "completed":
                    error = item.error or f"run failed: {item.id}"
                    if not reply_text:
                        reply_text = error
                continue
            if not isinstance(item, ProductStreamEvent):
                continue
            typ = item.type
            payload = item.payload
            if typ == "thread.message.updated":
                if rt.has_sent_message_in_turn(run.id):
                    continue
                draft = accumulate(draft, payload)
                continue
            if typ == "thread.progress":
                thinking = accumulate(thinking, payload)
                continue
            event_type = ProductEventType(typ)
            _emit(events, bot, event_type, payload, run_id=run.id)
    except asyncio.CancelledError:
        waiting = None
        try:
            waiting = history.waiting_takeover_run(bot.id)
        except Exception:
            waiting = None
        if waiting is not None and waiting.id == run.id:
            log.info("turn %s waiting for takeover", run.id)
            return
        status = "cancelled"
        error = "Stopped."
        reply_text = ""
        log.info("turn %s cancelled", run.id)
    except AgentRuntimeError as err:
        status = "failed"
        error = err.message
        reply_text = err.message
        log.error(
            "run did not start: %s retryable=%s request_id=%s",
            err.message,
            err.retryable,
            err.request_id,
        )
    except Exception as err:
        status = "failed"
        error = str(err)
        reply_text = str(err)
        log.exception("run failed")
    finally:
        _drop_turn(bot.id, run.id)

    has_sent = rt.has_sent_message_in_turn(run.id)
    rt.clear_active_turn(run_id=run.id)

    if status == "cancelled":
        reply_text = ""
    elif has_sent:
        reply_text = error if status != "completed" else ""
    elif not reply_text:
        reply_text = draft or error or ""

    try:
        bot_msg, finished = history.finish_turn(bot, run, reply_text, status, error=error)
    except DatabaseUnavailable:
        log.exception("failed to persist turn finish")
        _emit(
            events,
            bot,
            ProductEventType.RUN_FAILED,
            {"error": "history unavailable", "retryable": True},
            run_id=run.id,
        )
        return

    if bot_msg is not None:
        _emit(
            events,
            bot,
            ProductEventType.THREAD_MESSAGE_CREATED,
            {"message": bot_msg.model_dump(mode="json")},
            run_id=finished.id,
        )
    final_type = (
        ProductEventType.RUN_COMPLETED if status == "completed" else ProductEventType.RUN_FAILED
    )
    if status == "cancelled":
        final_type = ProductEventType.RUN_CANCELLED
    _emit(
        events,
        bot,
        final_type,
        {"run": finished.model_dump(mode="json"), "error": error},
        run_id=finished.id,
    )
    if status == "completed":
        hub = _memory_hub(rt)
        if hub is not None:
            try:
                for entry in hub.extract_after_turn(text, run.id, bot.id):
                    _emit_remembered(events, bot, entry.text, run.id)
            except Exception:
                log.exception("failed to extract memory after turn")
    if status != "cancelled":
        await _kick_inbox(history, rt, events, bot)


def _format_inbox(
    history: HistoryStore,
    bot: Bot,
    items: list[dict[str, str | None]],
    ) -> str:
    lines = [
        "The user sent these messages while you were working. They were not injected mid-turn. Apply them now.",
        "- If a message asks about progress, status, or a worker (e.g. 'еще делаешь?', 'сверил?', 'как там?'): check the actual state immediately (using inspect_subagent, list_subagents, or shell), give a quick direct update, and if a worker is stuck or failing, stop it (stop_subagent) and finish or fix the task directly.",
        "- If a message refines or corrects a worker's task: steer it immediately with steer_subagent.",
        "- If a message gives new substantive parallel tasks: spawn a subagent if appropriate, or execute directly.",
    ]
    for index, item in enumerate(items, start=1):
        text = item.get("text") or ""
        reply_id = item.get("reply_to_id")
        if reply_id:
            reply = history.get_message_in_thread(bot.thread_id, reply_id)
            if reply is not None:
                lines.append(f"{index}. (reply to {_message_excerpt(reply)!r}) {text}")
                continue
        lines.append(f"{index}. {text}")
    return "\n".join(lines)


async def _kick_inbox(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
) -> None:
    try:
        live = history.get_bot(bot.id) or bot
        claimed = history.claim_inbox_follow_up(
            live,
            model_provider=runtime_kind(rt.settings),
            model_id=rt.settings.cursor_model,
        )
    except Exception:
        log.exception("failed to claim inbox")
        return
    if claimed is None:
        return
    run, items = claimed
    _emit(
        events,
        live,
        ProductEventType.RUN_STARTED,
        {"run": run.model_dump(mode="json")},
        run_id=run.id,
    )
    task = asyncio.create_task(
        _run_turn(
            history,
            rt,
            events,
            live,
            _format_inbox(history, live, items),
            run,
            session_id=live.cursor_agent_id,
            attach_agent=True,
        ),
        name=f"turn-{run.id}",
    )
    _register_turn(live.id, run.id, task)


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


@app.post("/v1/devices/pairing", dependencies=[Depends(require_host)])
async def create_pairing(history: HistoryStore = Depends(store)) -> PairingCode:
    try:
        return history.create_pairing_code()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/devices")
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


@app.get("/v1/devices", dependencies=[Depends(require_auth)])
async def list_devices(history: HistoryStore = Depends(store)) -> DeviceList:
    try:
        return DeviceList(devices=history.list_devices())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.delete("/v1/devices/{device_id}")
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


@app.get("/v1/models", dependencies=[Depends(require_auth)])
async def list_models(rt: AgentRuntime = Depends(runtime)) -> dict[str, Any]:
    return {"models": await rt.list_models()}


@app.get("/v1/session", dependencies=[Depends(require_auth)])
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


@app.post("/v1/session", dependencies=[Depends(require_auth)])
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


@app.get("/v1/me", dependencies=[Depends(require_auth)])
async def get_me() -> Me:
    return Me()


@app.get("/v1/deployment", dependencies=[Depends(require_auth)])
async def get_deployment() -> DeploymentSettings:
    return DeploymentSettings()


@app.patch("/v1/deployment", dependencies=[Depends(require_auth)])
async def update_deployment(body: UpdateDeploymentInput) -> DeploymentSettings:
    return DeploymentSettings(
        signups_enabled=body.signups_enabled if body.signups_enabled is not None else True,
        signup_allowlist=body.signup_allowlist if body.signup_allowlist is not None else [],
        computer_host=body.computer_host if body.computer_host is not None else "docker",
    )


@app.get("/v1/bots", dependencies=[Depends(require_auth)])
async def list_bots(history: HistoryStore = Depends(store)) -> BotList:
    try:
        return BotList(bots=history.list_bots())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/bots/archived", dependencies=[Depends(require_auth)])
async def list_archived_bots(history: HistoryStore = Depends(store)) -> BotList:
    try:
        return BotList(bots=history.list_archived_bots())
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/bots/{bot_id}", dependencies=[Depends(require_auth)])
async def get_bot(bot_id: str, history: HistoryStore = Depends(store)) -> Bot:
    try:
        return _require_bot(history, bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/bots", dependencies=[Depends(require_auth)])
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


@app.post("/v1/bots/{bot_id}/duplicate", dependencies=[Depends(require_auth)])
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


@app.patch("/v1/bots/{bot_id}", dependencies=[Depends(require_auth)])
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


@app.get("/v1/bots/{bot_id}/subagents", dependencies=[Depends(require_auth)])
async def list_subagents(bot_id: str, history: HistoryStore = Depends(store)) -> SubagentList:
    try:
        bot = _require_bot(history, bot_id)
        return SubagentList(subagents=history.list_subagents(bot.id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/bots/{bot_id}/subagents/{subagent_id}/stop", dependencies=[Depends(require_auth)])
async def stop_subagent(
    bot_id: str,
    subagent_id: str,
    history: HistoryStore = Depends(store),
) -> Subagent:
    try:
        bot = _require_bot(history, bot_id)
        service = getattr(app.state, "subagents", None)
        if service is None:
            raise HTTPException(status_code=503, detail="subagents unavailable")
        return service.stop(bot, subagent_id)
    except SubagentError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/bots/{bot_id}/subagents/{subagent_id}/restart", dependencies=[Depends(require_auth)])
async def restart_subagent(
    bot_id: str,
    subagent_id: str,
    history: HistoryStore = Depends(store),
) -> Subagent:
    try:
        bot = _require_bot(history, bot_id)
        service = getattr(app.state, "subagents", None)
        if service is None:
            raise HTTPException(status_code=503, detail="subagents unavailable")
        return service.restart(bot, subagent_id)
    except SubagentError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/bots/{bot_id}/subagents/{subagent_id}/steer", dependencies=[Depends(require_auth)])
async def steer_subagent(
    bot_id: str,
    subagent_id: str,
    body: SteerSubagentInput,
    history: HistoryStore = Depends(store),
) -> Subagent:
    try:
        bot = _require_bot(history, bot_id)
        service = getattr(app.state, "subagents", None)
        if service is None:
            raise HTTPException(status_code=503, detail="subagents unavailable")
        return service.steer(bot, subagent_id, body.text)
    except SubagentError as err:
        if str(err) == "subagent not found":
            raise HTTPException(status_code=404, detail=str(err)) from err
        raise HTTPException(status_code=409, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/bots/{bot_id}/computer", dependencies=[Depends(require_auth)])
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


@app.post("/v1/bots/{bot_id}/archive", dependencies=[Depends(require_auth)])
async def archive_bot(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        _require_bot(history, bot_id)
        history.archive_bot(bot_id)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/bots/{bot_id}/restore", dependencies=[Depends(require_auth)])
async def restore_bot(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        restored = history.restore_bot(bot_id)
        if restored is None:
            raise HTTPException(status_code=404, detail="bot not found")
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.delete("/v1/bots/{bot_id}", dependencies=[Depends(require_auth)])
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
        service = getattr(app.state, "subagents", None)
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
    shutil.rmtree(Path(app.state.settings.agent_data_dir) / "artifacts" / bot_id, ignore_errors=True)
    return OkResponse(ok=True)


@app.get("/v1/threads/{bot_id}", dependencies=[Depends(require_auth)])
async def get_thread(bot_id: str, history: HistoryStore = Depends(store)) -> ThreadSnapshot:
    try:
        bot = _require_bot(history, bot_id)
        return _snapshot(history, bot)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/threads/{bot_id}/messages", dependencies=[Depends(require_auth)])
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


@app.post("/v1/threads/{bot_id}/messages")
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


@app.post("/v1/threads/{bot_id}/attachments", dependencies=[Depends(require_auth)])
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


@app.get("/v1/consents/{consent_id}")
async def get_consent(
    consent_id: str,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> ConsentJob:
    job = hub.get_job(consent_id)
    if job is None:
        raise HTTPException(status_code=404, detail="consent not found")
    return ConsentJob.model_validate(job)


@app.post("/v1/consents/{consent_id}")
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


@app.post("/v1/consents/{consent_id}/file")
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


@app.post("/v1/consents/{consent_id}/result")
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


@app.get("/v1/artifacts", dependencies=[Depends(require_auth)])
async def list_artifacts(
    bot_id: str = Query(...),
    history: HistoryStore = Depends(store),
) -> ArtifactList:
    try:
        _require_bot(history, bot_id)
        return ArtifactList(artifacts=history.list_artifacts(bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/artifacts/{artifact_id}", dependencies=[Depends(require_auth)])
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
    root = (Path(app.state.settings.agent_data_dir) / "artifacts").resolve()
    path = Path(stored).resolve()
    try:
        path.relative_to(root)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="file not found") from err
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, filename=artifact.name, media_type=artifact.mime_type)


@app.post("/v1/threads/{bot_id}/stop", dependencies=[Depends(require_auth)])
async def stop_thread(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> OkResponse:
    try:
        bot = _require_bot(history, bot_id)
        _cancel_turns(bot_id)
        service = getattr(app.state, "subagents", None)
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


@app.post("/v1/threads/{bot_id}/follow-up")
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


@app.post("/v1/threads/{bot_id}/read", dependencies=[Depends(require_auth)])
async def mark_thread_read(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        _require_bot(history, bot_id)
        history.set_bot_unread(bot_id, False)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/threads/{bot_id}/unread", dependencies=[Depends(require_auth)])
async def mark_thread_unread(bot_id: str, history: HistoryStore = Depends(store)) -> OkResponse:
    try:
        _require_bot(history, bot_id)
        history.set_bot_unread(bot_id, True)
        return OkResponse(ok=True)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/events", dependencies=[Depends(require_auth)])
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


@app.get("/v1/threads/{bot_id}/events", dependencies=[Depends(require_auth)])
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


@app.get("/v1/messages", dependencies=[Depends(require_auth)])
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


@app.get("/v1/memory", dependencies=[Depends(require_auth)])
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


@app.post("/v1/memory", dependencies=[Depends(require_auth)])
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


@app.get("/v1/memory/export", dependencies=[Depends(require_auth)])
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


@app.patch("/v1/memory/{document_id}", dependencies=[Depends(require_auth)])
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


@app.delete("/v1/memory/{document_id}", dependencies=[Depends(require_auth)])
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


@app.get("/v1/routines", dependencies=[Depends(require_auth)])
async def list_routines(
    bot_id: str = Query(...),
    history: HistoryStore = Depends(store),
) -> RoutineList:
    try:
        _require_bot(history, bot_id)
        return RoutineList(routines=history.list_routines(bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/routines", dependencies=[Depends(require_auth)])
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


@app.patch("/v1/routines/{routine_id}", dependencies=[Depends(require_auth)])
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


@app.delete("/v1/routines/{routine_id}", dependencies=[Depends(require_auth)])
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


@app.post("/v1/routines/{routine_id}/test")
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


@app.post("/v1/runs")
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


@app.get("/v1/computer/{bot_id}", dependencies=[Depends(require_auth)])
async def computer_status(
    bot_id: str,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        return boxes.status(_require_bot(history, bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/computer/{bot_id}/boot", dependencies=[Depends(require_auth)])
async def computer_boot(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.boot(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@app.post("/v1/computer/{bot_id}/stop", dependencies=[Depends(require_auth)])
async def computer_stop(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.stop(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@app.post("/v1/computer/{bot_id}/restart", dependencies=[Depends(require_auth)])
async def computer_restart(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.restart(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@app.post("/v1/computer/{bot_id}/reset", dependencies=[Depends(require_auth)])
async def computer_reset(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> ComputerStatus:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.reset(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit_computer(events, bot, status)
    return status


@app.post("/v1/computer/{bot_id}/takeover", dependencies=[Depends(require_auth)])
async def computer_takeover(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> TakeoverResult:
    try:
        bot = _require_bot(history, bot_id)
        result = boxes.takeover(bot)
        status = boxes.status(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit(
        events,
        bot,
        ProductEventType.COMPUTER_TAKEOVER_GRANTED,
        {"lease_id": result.lease_id, "expires_at": result.expires_at},
    )
    _emit_computer(events, bot, status)
    return result


@app.post("/v1/computer/{bot_id}/release", dependencies=[Depends(require_auth)])
async def computer_release(
    bot_id: str,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
    boxes: ComputerService = Depends(computers),
) -> OkResponse:
    try:
        bot = _require_bot(history, bot_id)
        status = boxes.release(bot)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    _emit(events, bot, ProductEventType.COMPUTER_TAKEOVER_RELEASED, {})
    _emit_computer(events, bot, status)
    return OkResponse(ok=True)


@app.post("/v1/computer/{bot_id}/heartbeat", dependencies=[Depends(require_auth)])
async def computer_heartbeat(
    bot_id: str,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> OkResponse:
    try:
        boxes.heartbeat(_require_bot(history, bot_id))
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return OkResponse(ok=True)


@app.get("/v1/computer/{bot_id}/screen", dependencies=[Depends(require_auth)])
async def computer_screen(
    bot_id: str,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ScreenUrlResult:
    try:
        return boxes.screen_url(_require_bot(history, bot_id))
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.post("/v1/computer/{bot_id}/input", dependencies=[Depends(require_auth)])
async def computer_input(
    bot_id: str,
    body: ComputerInput,
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> OkResponse:
    try:
        boxes.send_input(_require_bot(history, bot_id), body.kind, body.payload)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return OkResponse(ok=True)


@app.get("/v1/computer/{bot_id}/files", dependencies=[Depends(require_auth)])
async def computer_files(
    bot_id: str,
    path: str = Query(default="/"),
    hidden: bool = Query(default=False),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ComputerFileList:
    try:
        return boxes.list_files(_require_bot(history, bot_id), path, hidden=hidden)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/computer/{bot_id}/files/read", dependencies=[Depends(require_auth)])
async def computer_read_file(
    bot_id: str,
    path: str = Query(...),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> ComputerFileContent:
    try:
        return boxes.read_file(_require_bot(history, bot_id), path)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@app.get("/v1/computer/{bot_id}/files/raw", dependencies=[Depends(require_auth)])
async def computer_download_file(
    bot_id: str,
    path: str = Query(...),
    history: HistoryStore = Depends(store),
    boxes: ComputerService = Depends(computers),
) -> FileResponse:
    try:
        target, name, mime = boxes.file_for_download(_require_bot(history, bot_id), path)
    except (ComputerBusy, ComputerError) as err:
        raise _computer_http(err) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return FileResponse(target, filename=name, media_type=mime)


@app.api_route("/novnc/{rest:path}", methods=["GET", "HEAD"], dependencies=[Depends(require_auth)])
async def novnc_http(rest: str, request: Request) -> Response:
    return await proxy_novnc_http(request, request.app.state.settings.agent_http_token)


@app.websocket("/novnc/{rest:path}")
async def novnc_ws(websocket: WebSocket, rest: str) -> None:
    try:
        await _authorize_websocket(websocket)
    except HTTPException as err:
        code = 4401 if err.status_code == 401 else 4403
        await websocket.close(code=code)
        return
    await proxy_novnc_ws(websocket, websocket.app.state.settings.agent_http_token)
