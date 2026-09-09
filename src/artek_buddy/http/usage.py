from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from artek_buddy.contracts import UsageRecordList, UsageSummary
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, _require_bot, require_auth, store

router = APIRouter()


@router.get(
    "/v1/usage",
    dependencies=[Depends(require_auth)],
    response_model_exclude_none=True,
)
async def list_usage(
    bot_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    history: HistoryStore = Depends(store),
) -> UsageRecordList:
    try:
        if bot_id:
            _require_bot(history, bot_id)
        return history.list_usage(bot_id=bot_id, run_id=run_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err


@router.get(
    "/v1/usage/summary",
    dependencies=[Depends(require_auth)],
    response_model_exclude_none=True,
)
async def usage_summary(
    bot_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    history: HistoryStore = Depends(store),
) -> UsageSummary:
    try:
        if bot_id:
            _require_bot(history, bot_id)
        return history.usage_summary(bot_id=bot_id, run_id=run_id)
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
