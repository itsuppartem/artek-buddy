from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query

from artek_buddy.bus import EventHub
from artek_buddy.contracts import (
    AutomationDryRun,
    AutomationRun,
    AutomationRunList,
    Bot,
    CreateRoutineInput,
    FireRoutineInput,
    OkResponse,
    Principal,
    ProductEventType,
    Routine,
    RoutineList,
    TestRunResult,
    UpdateRoutineInput,
)
from artek_buddy.cron import CronError
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import (
    _db_error,
    _require_bot,
    hub,
    require_auth,
    require_owner,
    runtime,
    store,
)
from artek_buddy.http.turns import (
    _accept_turn,
    _emit,
)
from artek_buddy.runtime import AgentRuntime

router = APIRouter()


def _publish_approval_ask(
    history: HistoryStore, events: EventHub, bot: Bot, auto_run: AutomationRun
) -> None:
    message_id = str(auto_run.snapshot.get("approval_message_id") or "")
    if not message_id:
        return
    message = history.get_message_in_thread(bot.thread_id, message_id)
    if message is None:
        return
    run = history.get_run(message.run_id) if message.run_id else None
    if run is not None:
        _emit(
            events,
            bot,
            ProductEventType.RUN_STARTED,
            {"run": run.model_dump(mode="json")},
            run_id=run.id,
        )
    _emit(
        events,
        bot,
        ProductEventType.THREAD_MESSAGE_CREATED,
        {"message": message.model_dump(mode="json")},
        run_id=message.run_id,
    )
    if run is not None:
        _emit(
            events,
            bot,
            ProductEventType.RUN_WAITING_INPUT,
            {"run_id": run.id},
            run_id=run.id,
        )


@router.get("/v1/routines")
async def list_routines(
    bot_id: str = Query(...),
    _principal: Principal = Depends(require_owner),
    history: HistoryStore = Depends(store),
) -> RoutineList:
    try:
        _require_bot(history, bot_id)
        return RoutineList(routines=history.list_routines(bot_id))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/routines")
async def create_routine(
    body: CreateRoutineInput,
    _principal: Principal = Depends(require_owner),
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
            body.require_approval,
        )
    except CronError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.patch("/v1/routines/{routine_id}")
async def update_routine(
    routine_id: str,
    body: UpdateRoutineInput,
    _principal: Principal = Depends(require_owner),
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
            require_approval=body.require_approval,
        )
    except CronError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if routine is None:
        raise HTTPException(status_code=404, detail="routine not found")
    return routine


@router.delete("/v1/routines/{routine_id}")
async def remove_routine(
    routine_id: str,
    _principal: Principal = Depends(require_owner),
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
    _principal: Principal = Depends(require_owner),
    rt: AgentRuntime = Depends(runtime),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> TestRunResult:
    try:
        routine = history.get_routine(routine_id)
        if routine is None:
            raise HTTPException(status_code=404, detail="routine not found")
        bot = _require_bot(history, routine.bot_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    result = await _accept_turn(
        history, rt, events, bot, routine.prompt, trigger="routine", device_id=actor
    )
    return TestRunResult(
        routine_id=routine.id,
        task_id=result.task_id,
        run_id=result.run_id,
        seq=result.seq,
    )


@router.post("/v1/routines/{routine_id}/run")
async def fire_routine(
    routine_id: str,
    body: FireRoutineInput | None = None,
    _principal: Principal = Depends(require_owner),
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> AutomationRun:
    payload = body or FireRoutineInput()
    event_id = (payload.trigger_event_id or "").strip() or secrets.token_hex(8)
    try:
        routine = history.get_routine(routine_id)
        if routine is None:
            raise HTTPException(status_code=404, detail="routine not found")
        _require_bot(history, routine.bot_id)
        auto_run = history.ensure_automation_run(
            routine,
            trigger_kind="manual",
            trigger_event_id=event_id,
            idempotency_key=f"manual:{routine.id}:{event_id}",
        )
        if auto_run.state == "waiting_for_approval":
            bot = _require_bot(history, routine.bot_id)
            if not auto_run.snapshot.get("approval_posted") and history.has_active_run(bot.id):
                raise HTTPException(status_code=409, detail="bot is busy")
            auto_run = history.ensure_approval_ask(bot, auto_run)
            _publish_approval_ask(history, events, bot, auto_run)
        elif auto_run.state == "queued":
            history.enqueue_automation_prompt(auto_run)
            refreshed = history.get_automation_run(auto_run.id)
            if refreshed is not None:
                auto_run = refreshed
        return auto_run
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.post("/v1/routines/{routine_id}/dry-run")
async def dry_run_routine(
    routine_id: str,
    _principal: Principal = Depends(require_owner),
    history: HistoryStore = Depends(store),
) -> AutomationDryRun:
    try:
        routine = history.get_routine(routine_id)
        if routine is None:
            raise HTTPException(status_code=404, detail="routine not found")
        return AutomationDryRun(
            snapshot=history.automation_snapshot(routine),
            dangerous_tools=False,
        )
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get("/v1/routines/{routine_id}/runs")
async def list_routine_runs(
    routine_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    _principal: Principal = Depends(require_owner),
    history: HistoryStore = Depends(store),
) -> AutomationRunList:
    try:
        routine = history.get_routine(routine_id)
        if routine is None:
            raise HTTPException(status_code=404, detail="routine not found")
        return AutomationRunList(runs=history.list_automation_runs(routine_id, limit=limit))
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
