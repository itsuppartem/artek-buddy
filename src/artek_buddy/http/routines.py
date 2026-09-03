from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query

from artek_buddy.bus import EventHub
from artek_buddy.contracts import (
    CreateRoutineInput,
    OkResponse,
    Routine,
    RoutineList,
    TestRunResult,
    UpdateRoutineInput,
)
from artek_buddy.cron import CronError
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.runtime import (
    AgentRuntime,
)

log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.deps import (
    _db_error,
    _require_bot,
    hub,
    require_auth,
    runtime,
    store,
)
from artek_buddy.http.turns import (
    _accept_turn,
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
