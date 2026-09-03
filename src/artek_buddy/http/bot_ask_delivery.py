"""Start and return bot-to-bot asks. Turn execution stays in ``http.turns``."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from artek_buddy.bot_asks import (
    asked_card_blocks,
    inbound_model_prompt,
    inbound_visible_text,
    last_bot_reply,
    normalize_question,
    ready_card_blocks,
    reply_model_prompt,
)
from artek_buddy.bus import EventHub
from artek_buddy.contracts import Bot, ProductEventType, Run, ThreadSendResult
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import current_app
from artek_buddy.runtime import AgentRuntime, runtime_kind

log = logging.getLogger("artek_buddy")


def _turns() -> Any:
    from artek_buddy.http import turns

    return turns


def handle_bot_ask(from_bot_id: str, dest_id: str, question: str, from_run_id: str | None) -> None:
    async def _go() -> None:
        app = current_app()
        history = getattr(app.state, "store", None)
        rt = getattr(app.state, "runtime", None)
        events = getattr(app.state, "hub", None)
        if history is None or rt is None or events is None:
            return
        source = history.get_bot(from_bot_id)
        dest = history.get_bot(dest_id)
        if source is None or dest is None:
            return
        try:
            await launch_bot_ask(
                history, rt, events, source, dest, question, from_run_id, post_card=False
            )
        except Exception:
            log.exception("failed to start asked bot %s", dest_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_go(), name=f"bot-ask-{dest_id}")
    except RuntimeError:
        loop = getattr(getattr(current_app().state, "runtime", None), "loop", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_go(), loop)


async def launch_bot_ask(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    source: Bot,
    dest: Bot,
    question: str,
    from_run_id: str | None,
    *,
    post_card: bool,
) -> ThreadSendResult:
    turns = _turns()
    question = normalize_question(question)
    if post_card:
        card = history.append_bot_message(source, asked_card_blocks(dest, question))
        turns._emit(
            events,
            source,
            ProductEventType.THREAD_MESSAGE_CREATED,
            {"message": card.model_dump(mode="json")},
            run_id=from_run_id,
        )
    history.create_bot_ask(
        from_bot_id=source.id,
        to_bot_id=dest.id,
        question=question,
        from_run_id=from_run_id,
    )
    return await turns._accept_turn(
        history,
        rt,
        events,
        dest,
        inbound_visible_text(source.name, question),
        trigger="user",
        model_prompt=inbound_model_prompt(source.name, question),
    )


async def deliver_bot_ask_reply(
    history: HistoryStore,
    rt: AgentRuntime,
    events: EventHub,
    bot: Bot,
    run: Run,
    status: str,
    error: str | None,
    reply_text: str,
) -> None:
    turns = _turns()
    take = getattr(history, "peek_undelivered_ask_for_run", None)
    if not callable(take):
        return
    page = history.page_messages(bot.thread_id, limit=40)
    answer = last_bot_reply(page.messages) or (reply_text or "").strip()
    if status == "cancelled":
        answer = f"{bot.name} was stopped."
    elif status != "completed":
        answer = f"{bot.name} failed." + (f" {error}" if error else "")
    elif not answer:
        answer = f"{bot.name} finished without a reply."
    pending = take(run.id)
    if pending is None:
        return
    source = history.get_bot(str(pending.get("from_bot_id") or ""))
    if source is None:
        return
    prompt = reply_model_prompt(bot.name, answer)
    live = source
    if history.active_run_count(source.id) == 0:
        live = await turns._ensure_agent(history, rt, source)
    delivered = history.deliver_bot_ask_follow_up(
        to_run_id=run.id,
        reply_text=answer,
        source=live,
        ready_blocks=ready_card_blocks(bot),
        prompt=prompt,
        model_provider=runtime_kind(rt.settings),
        model_id=turns._chosen_model_id(history, rt),
    )
    if delivered is None:
        return
    ask, ready, follow = delivered
    turns._emit(
        events,
        source,
        ProductEventType.THREAD_MESSAGE_CREATED,
        {"message": ready.model_dump(mode="json")},
        run_id=str(ask.get("from_run_id") or "") or None,
    )
    if follow is None:
        return
    turns._emit(
        events,
        live,
        ProductEventType.RUN_STARTED,
        {"run": follow.model_dump(mode="json")},
        run_id=follow.id,
    )
    task = asyncio.create_task(
        turns._run_turn(
            history,
            rt,
            events,
            live,
            prompt,
            follow,
            session_id=live.cursor_agent_id,
            attach_agent=True,
        ),
        name=f"turn-{follow.id}",
    )
    turns._register_turn(live.id, follow.id, task)
