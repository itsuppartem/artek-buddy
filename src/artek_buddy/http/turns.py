from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from artek_buddy.apps import format_apps_context
from artek_buddy.books import format_book_catalog
from artek_buddy.bot_asks import (
    ASKED_YOU_MARK,
    format_other_bots,
)
from artek_buddy.bus import EventHub
from artek_buddy.computer.service import (
    ComputerService,
)
from artek_buddy.contracts import (
    Bot,
    ComputerStatus,
    MessageRole,
    ProductEvent,
    ProductEventType,
    Run,
    ThreadMessage,
    ThreadSendResult,
)
from artek_buddy.db import DatabaseUnavailable, product_run_status
from artek_buddy.db.history import HistoryStore, InboxFullError
from artek_buddy.db.shaping import (
    DEFAULT_BOT_NAME,
    blocks_text,
    isoformat_utc,
    new_id,
    owner_visible_error,
    preview_snippet,
    text_blocks,
)
from artek_buddy.memory import (
    compact_thread_context,
    format_memory_context,
    format_subagent_context,
    wrap_turn_prompt,
)
from artek_buddy.memory_hub import MemoryHub, should_persist_ask
from artek_buddy.model_catalog import NEEDS_MODEL_TEXT, complete_chat
from artek_buddy.observe import (
    bind_turn,
    current_request_id,
    log_event,
    mint_request_id,
    unbind_turn,
)
from artek_buddy.runtime import (
    AgentRuntime,
    AgentRuntimeError,
    ProductStreamEvent,
    RunRecord,
    runtime_kind,
)
from artek_buddy.runtime.owner_intent import classify_owner_intent
from artek_buddy.status_ping import STATUS_PING_GUIDE
from artek_buddy.stream import accumulate
from artek_buddy.uploads import (
    UploadError,
    format_user_turn,
    ingest_uploads,
    preview_for_upload,
    user_file_blocks,
)

log = logging.getLogger("artek_buddy")

from artek_buddy.http.bot_ask_delivery import deliver_bot_ask_reply as _deliver_bot_ask_reply
from artek_buddy.http.deps import (
    MAX_INBOX,
    _db_error,
    current_app,
)
from artek_buddy.http.turn_registry import cancel_turns as _cancel_turns
from artek_buddy.http.turn_registry import drop_turn as _drop_turn
from artek_buddy.http.turn_registry import register_turn as _register_turn


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
    entry: Any | None = None,
) -> None:
    label = f"Remembered: {text}".strip() if text else "Remembered a note"
    _emit(events, bot, ProductEventType.THREAD_META, {"text": label[:160]}, run_id=run_id)
    payload: dict[str, Any] = {"text": (text or "")[:160]}
    document_id = getattr(entry, "document_id", None) if entry is not None else None
    if document_id:
        payload["document_id"] = document_id
    scope = getattr(entry, "scope", None) if entry is not None else None
    if scope:
        payload["scope"] = scope
    kind = getattr(entry, "kind", None) if entry is not None else None
    if kind:
        payload["kind"] = kind
    slot = getattr(entry, "slot", None) if entry is not None else None
    if slot:
        payload["section"] = slot
    _emit(events, bot, ProductEventType.MEMORY_REVISED, payload, run_id=run_id)


def _emit_computer(events: EventHub, bot: Bot, status: ComputerStatus) -> None:
    payload = status.model_dump(mode="json")
    payload["status"] = status.state
    _emit(events, bot, ProductEventType.COMPUTER_STATUS, payload)


def _memory_hub(rt: AgentRuntime | None = None) -> MemoryHub | None:
    if rt is not None:
        found = getattr(rt, "memory", None)
        if found is not None:
            return found
    return getattr(current_app().state, "memory", None)


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
                _emit_remembered(events, bot, entry.text, run_id, entry=entry)
        except Exception:
            log.exception("failed to capture ask answer in memory")


async def _shutdown_work() -> None:
    pending: list[asyncio.Task[Any]] = []
    turns = getattr(current_app().state, "active_turns", None)
    if turns:
        for bucket in list(turns.values()):
            for task in list(bucket.values()):
                if task and not task.done():
                    task.cancel()
                    pending.append(task)
    service = getattr(current_app().state, "subagents", None)
    history = getattr(current_app().state, "store", None)
    if service is not None and history is not None:
        try:
            for bot in history.list_bots():
                service.stop_all(bot)
        except Exception:
            log.exception("failed to stop subagents during shutdown")
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _block_dicts(message: ThreadMessage) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    for block in message.blocks or []:
        if hasattr(block, "model_dump"):
            raw.append(block.model_dump())
        elif isinstance(block, dict):
            raw.append(block)
    return raw


def _message_excerpt(message: ThreadMessage, limit: int = 400) -> str:
    return preview_snippet(blocks_text(_block_dicts(message)), limit)


def _posted_bot_texts(history: HistoryStore, bot: Bot, run_id: str) -> set[str]:
    posted: set[str] = set()
    for msg in history.page_messages(bot.thread_id, limit=200).messages:
        if msg.run_id != run_id or msg.role != MessageRole.bot:
            continue
        for block in _block_dicts(msg):
            if block.get("kind") != "text":
                continue
            text = str(block.get("text") or "").strip()
            if text:
                posted.add(text)
    return posted


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


async def _ensure_agent(history: HistoryStore, rt: AgentRuntime, bot: Bot) -> Bot:
    stamp = history.model_fingerprint()
    live = history.has_active_run(bot.id)
    mismatch = bool(stamp) and history.applied_model(bot.id) != stamp
    if mismatch and not live:
        live_id = await rt.create_session(
            name=bot.name or DEFAULT_BOT_NAME,
            persist_default=False,
            bot_id=bot.id,
        )
        history.mark_applied_model(bot.id, stamp)
    else:
        live_id = await rt.ensure_session(
            bot.cursor_agent_id,
            name=bot.name or DEFAULT_BOT_NAME,
            bot_id=bot.id,
        )
        if stamp and not (mismatch and live):
            history.mark_applied_model(bot.id, stamp)
    rt.bind_agent_bot(live_id, bot.id)
    if bot.cursor_agent_id != live_id:
        return history.attach_agent(bot.id, live_id)
    return bot


def _handle_takeover_request(bot_id: str, run_id: str | None, reason: str | None = None) -> None:
    history: HistoryStore = current_app().state.store
    events: EventHub = current_app().state.hub
    service: ComputerService = current_app().state.computers
    bot = history.get_bot(bot_id)
    if bot is None:
        return
    text = (
        reason or ""
    ).strip() or "Take control of this computer, then Release when you are done."
    try:
        msg = history.append_bot_message(
            bot,
            [{"kind": "computer", "state": "waiting", "text": text}],
            run_id=run_id,
        )
        _emit(
            events,
            bot,
            ProductEventType.THREAD_MESSAGE_CREATED,
            {"message": msg.model_dump(mode="json")},
            run_id=run_id,
        )
        history.set_bot_unread(bot_id, True)
        service.release(bot)
        _emit(
            events,
            bot,
            ProductEventType.COMPUTER_TAKEOVER_REQUESTED,
            {"run_id": run_id, "reason": text},
            run_id=run_id,
        )
        _emit_computer(events, bot, service.status(bot))
    except Exception:
        log.exception("takeover request failed")
    _cancel_turns(bot_id, run_id)


def _resume_parked_takeover(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
) -> None:
    parked = history.waiting_takeover_run(bot.id)
    if parked is None:
        return
    live = history.mark_run_running(parked.id)
    if live is None:
        return
    prompt = "The owner released the desktop. Continue the same task."
    _emit(
        events,
        bot,
        ProductEventType.RUN_STARTED,
        {"run": live.model_dump(mode="json")},
        run_id=live.id,
    )

    async def _go() -> None:
        try:
            bot2 = await _ensure_agent(history, rt, bot)
            await _run_turn(
                history,
                rt,
                events,
                bot2,
                prompt,
                live,
                session_id=bot2.cursor_agent_id,
            )
        except Exception:
            log.exception("failed to resume parked takeover run")

    task = asyncio.create_task(_go(), name=f"turn-{live.id}")
    _register_turn(bot.id, live.id, task)


def _format_inbox(
    history: HistoryStore,
    bot: Bot,
    items: list[dict[str, str | None]],
) -> str:
    lines = [
        "The user sent these messages while you were working. They were not injected mid-turn. Apply them now.",
        f"- {STATUS_PING_GUIDE} When a step is stored, say that step.",
        "- If a message refines or corrects a worker's task: steer it immediately with steer_subagent. Keep the same worker id. Do not stop and spawn a replacement.",
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


def _chosen_model_id(history: HistoryStore, rt: AgentRuntime) -> str:
    default = history.get_default_model()
    if default is not None:
        return default[1]
    return rt.settings.cursor_model


def _needs_model_send(
    history: HistoryStore,
    events: EventHub,
    bot: Bot,
    text: str,
) -> ThreadSendResult:
    display = (text or "").strip() or " "
    user_msg = history.append_user_message(bot, display)
    notice = history.append_bot_message(bot, [{"kind": "text", "text": NEEDS_MODEL_TEXT}])
    _emit(
        events,
        bot,
        ProductEventType.THREAD_MESSAGE_CREATED,
        {"message": user_msg.model_dump(mode="json")},
    )
    _emit(
        events,
        bot,
        ProductEventType.THREAD_MESSAGE_CREATED,
        {"message": notice.model_dump(mode="json")},
    )
    return ThreadSendResult(
        task_id=new_id("task"),
        run_id=new_id("run"),
        seq=user_msg.seq,
        message=user_msg,
        run=None,
        queued=False,
    )


async def _turn_stream(
    history: HistoryStore,
    rt: AgentRuntime,
    prompt: str,
    agent_id: str,
    bot: Bot,
):
    default = history.get_default_model()
    if runtime_kind(rt.settings) != "scripted" and default and default[0] != "cursor":
        provider, model = default
        key = history.raw_key(provider)
        text = await complete_chat(provider, key, model, prompt) if key else ""
        yield ProductStreamEvent(
            "thread.message.updated",
            {"text": text, "kind": "text", "replace": True},
        )
        yield RunRecord(id=new_id("run"), agent_id=agent_id, status="completed", result=text)
        return
    async for item in rt.stream(prompt, session_id=agent_id, bot_id=bot.id):
        yield item


async def _accept_turn(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
    text: str,
    trigger: str = "user",
    reply_to_id: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    model_prompt: str | None = None,
    device_id: str | None = None,
) -> ThreadSendResult:
    from artek_buddy.bot_credentials import apply_chat_credentials

    credential_store = getattr(rt, "credential_store", None)
    if credential_store is None:
        raise HTTPException(status_code=503, detail="credential broker unavailable")
    text = apply_chat_credentials(credential_store, bot.id, text)
    try:
        if history.get_default_model() is None:
            return _needs_model_send(history, events, bot, text)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    bot = await _ensure_agent(history, rt, bot)
    hosted = attachments or []
    display = (text or "").strip()
    stored = display
    prompt = (
        model_prompt
        if model_prompt is not None
        else (format_user_turn(display, hosted) if hosted else display)
    )
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
            stored if model_prompt is not None else prompt,
            model_provider=runtime_kind(rt.settings),
            model_id=_chosen_model_id(history, rt),
            trigger=trigger,
            reply_to_id=reply_msg.id if reply_msg else None,
            max_inbox=MAX_INBOX,
            blocks=(
                text_blocks(stored)
                if model_prompt is not None
                else (user_file_blocks(display, hosted) if hosted else None)
            ),
            preview=(
                display
                if model_prompt is not None
                else (preview_for_upload(display, hosted) if hosted else None)
            ),
            inbox_text=prompt,
        )
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    except InboxFullError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err

    request_id = current_request_id() or mint_request_id()
    bind_turn(
        run.id,
        request_id,
        bot_id=bot.id,
        thread_id=bot.thread_id,
        runtime=runtime_kind(rt.settings),
    )
    log_event(
        "threads.send",
        request_id=request_id,
        bot_id=bot.id,
        thread_id=bot.thread_id,
        turn_id=run.id,
        runtime=runtime_kind(rt.settings),
        result="queued" if queued else "started",
    )
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
            device_id=device_id,
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
    device_id: str | None = None,
) -> None:
    remembered = None
    getter = getattr(rt, "device_for_run", None)
    if callable(getter):
        remembered = getter(run.id)
    rt.clear_active_turn(run_id=run.id)
    agent_id = session_id or bot.cursor_agent_id
    rt.set_current_turn_context(
        bot.id,
        run.id,
        bot.thread_id,
        agent_id=agent_id,
        role="lead",
        device_id=device_id or remembered,
    )
    set_intent = getattr(rt, "set_owner_intent", None)
    if callable(set_intent):
        set_intent(run.id, classify_owner_intent(text))
    request_id = current_request_id() or mint_request_id()
    bind_turn(
        run.id,
        request_id,
        bot_id=bot.id,
        thread_id=bot.thread_id,
        runtime=runtime_kind(rt.settings),
    )
    draft = ""
    thinking = ""
    reply_text = ""
    error: str | None = None
    status = "failed"
    if ASKED_YOU_MARK in (text or ""):
        try:
            history.bind_pending_ask_run(bot.id, run.id)
        except Exception:
            log.exception("failed to bind asked turn %s", run.id)
    try:
        page = history.page_messages(bot.thread_id, limit=40)
        thread_context = compact_thread_context(page.messages, exclude_run_id=run.id)
        session_resume = (
            rt.build_session_resume(bot.id) if rt.consume_session_fresh(agent_id) else None
        )
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
            other_bots=format_other_bots(history.list_bots(), bot.id),
            books_context=format_book_catalog(history.list_skill_books(bot.id)),
            apps_context=format_apps_context(history),
            session_resume=session_resume,
        )
        async for item in _turn_stream(history, rt, memory_prompt, agent_id, bot):
            if isinstance(item, RunRecord):
                if attach_agent and item.agent_id and item.agent_id != bot.cursor_agent_id:
                    bot = history.attach_agent(bot.id, item.agent_id)
                    rt.bind_agent_bot(item.agent_id, bot.id)
                elif item.agent_id:
                    rt.bind_agent_bot(item.agent_id, bot.id)
                status = product_run_status(item.status)
                reply_text = item.result or draft or ""
                if status != "completed":
                    error = owner_visible_error(item.error, item.id)
                    if not reply_text or reply_text.strip() == error:
                        reply_text = ""
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
        unbind_turn(run.id)

    has_sent = rt.has_sent_message_in_turn(run.id)
    has_terminal = rt.has_sent_terminal_message_in_turn(run.id)
    rt.clear_active_turn(run_id=run.id)

    if status == "cancelled":
        reply_text = ""
    elif status != "completed":
        error = owner_visible_error(error, run.id)
        if has_sent or not reply_text or reply_text.strip() == error:
            reply_text = ""
    elif has_terminal:
        reply_text = ""
    elif has_sent:
        body = (reply_text or "").strip()
        if not body or body in _posted_bot_texts(history, bot, run.id):
            reply_text = ""
    elif not reply_text:
        reply_text = draft or ""

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

    persist_status = getattr(finished.status, "value", None) or str(finished.status)
    if persist_status == "cancelled":
        status = "cancelled"
        error = finished.error or "Stopped."
        bot_msg = None

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
        {
            "run": finished.model_dump(mode="json"),
            "error": error,
            "message": bot_msg.model_dump(mode="json") if bot_msg is not None else None,
        },
        run_id=finished.id,
    )
    if status == "completed":
        hub = _memory_hub(rt)
        if hub is not None:
            try:
                for entry in await hub.revise_after_turn(text, run.id, bot.id):
                    _emit_remembered(events, bot, entry.text, run.id, entry=entry)
            except Exception:
                log.exception("failed to extract memory after turn")
    try:
        await _deliver_bot_ask_reply(history, rt, events, bot, finished, status, error, reply_text)
    except Exception:
        log.exception("failed to return asked reply from %s", bot.id)
    if status != "cancelled":
        await _kick_inbox(history, rt, events, bot)


async def _kick_inbox(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
) -> None:
    try:
        live = history.get_bot(bot.id) or bot
        live = await _ensure_agent(history, rt, live)
        claimed = history.claim_inbox_follow_up(
            live,
            model_provider=runtime_kind(rt.settings),
            model_id=_chosen_model_id(history, rt),
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
