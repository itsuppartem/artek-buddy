from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import Depends, HTTPException, Query

from artek_buddy.bot_asks import BotAskError, normalize_question, resolve_ask
from artek_buddy.bot_credentials import BotCredentialStore
from artek_buddy.bus import EventHub
from artek_buddy.computer.service import (
    ComputerBusy,
    ComputerError,
    ComputerService,
)
from artek_buddy.contracts import (
    Bot,
    BotAskInput,
    BotAskResult,
    BotList,
    CreateBotInput,
    OkResponse,
    SetComputerInput,
    SteerSubagentInput,
    Subagent,
    SubagentList,
    UpdateBotInput,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.fs_jail import contained_under
from artek_buddy.runtime import (
    AgentRuntime,
)
from artek_buddy.subagents import SubagentError

log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.bot_ask_delivery import launch_bot_ask as _launch_bot_ask
from artek_buddy.http.deps import (
    _computer_http,
    _db_error,
    _require_bot,
    computers,
    current_app,
    hub,
    require_auth,
    runtime,
    store,
)
from artek_buddy.http.turns import (
    _cancel_turns,
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
    agent_id = await rt.create_session(name=body.name, persist_default=False)
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


@router.post(
    "/v1/bots/{bot_id}/subagents/{subagent_id}/restart", dependencies=[Depends(require_auth)]
)
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


@router.post(
    "/v1/bots/{bot_id}/subagents/{subagent_id}/steer", dependencies=[Depends(require_auth)]
)
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


@router.post("/v1/bots/{bot_id}/asks", dependencies=[Depends(require_auth)])
async def ask_other_bot(
    bot_id: str,
    body: BotAskInput,
    history: HistoryStore = Depends(store),
    rt: AgentRuntime = Depends(runtime),
    events: EventHub = Depends(hub),
) -> BotAskResult:
    from artek_buddy.bot_credentials import raise_if_pasted_credential

    raise_if_pasted_credential(body.text)
    try:
        source = _require_bot(history, bot_id)
        dest = resolve_ask(history, source, body.text, body.bot)
        sent = await _launch_bot_ask(
            history,
            rt,
            events,
            source,
            dest,
            normalize_question(body.text),
            None,
            post_card=True,
        )
    except BotAskError as err:
        raise HTTPException(status_code=err.status, detail=err.detail) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return BotAskResult(ok=True, to_bot_id=dest.id, to_run_id=sent.run_id, name=dest.name)


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
    dest = contained_under(Path(current_app().state.settings.agent_data_dir) / "artifacts", bot.id)
    if dest is not None:
        shutil.rmtree(dest, ignore_errors=True)
    BotCredentialStore(current_app().state.settings.agent_data_dir).forget_bot(bot.id)
    return OkResponse(ok=True)
