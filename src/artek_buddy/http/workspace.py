from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.bus import EventHub
from artek_buddy.contracts import WorkspaceDispatchInput, WorkspaceDispatchResult
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, hub, require_auth, runtime, store
from artek_buddy.http.turns import _accept_turn
from artek_buddy.runtime import AgentRuntime
from artek_buddy.workspace_dispatch import choose_workspace_bot

router = APIRouter()


@router.post(
    "/v1/workspace/dispatch",
    response_model=WorkspaceDispatchResult,
    dependencies=[Depends(require_auth)],
)
async def dispatch_workspace_task(
    body: WorkspaceDispatchInput,
    history: HistoryStore = Depends(store),
    rt: AgentRuntime = Depends(runtime),
    events: EventHub = Depends(hub),
) -> WorkspaceDispatchResult:
    try:
        target = await choose_workspace_bot(history, rt, body.text)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    except ValueError as err:
        message = str(err)
        status = 409 if message.startswith("create a bot") else 502
        raise HTTPException(status_code=status, detail=message) from err

    sent = await _accept_turn(history, rt, events, target, body.text.strip())
    return WorkspaceDispatchResult(
        bot_id=target.id,
        bot_name=target.name,
        task_id=sent.task_id,
        run_id=sent.run_id,
        seq=sent.seq,
        queued=sent.queued,
    )
