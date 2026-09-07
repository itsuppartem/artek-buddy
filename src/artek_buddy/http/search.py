from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from artek_buddy.contracts.domain import Principal
from artek_buddy.contracts.search import SearchPage
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.history.search import SearchTimeoutError
from artek_buddy.http.deps import _db_error, require_principal, store

router = APIRouter()


@router.get("/v1/search", response_model=SearchPage)
async def search(
    q: str = Query(default="", max_length=200),
    kinds: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(require_principal),
    history: HistoryStore = Depends(store),
) -> SearchPage:
    try:
        return history.search_documents(
            principal,
            query=q,
            kinds=kinds,
            cursor=cursor,
            limit=limit,
        )
    except SearchTimeoutError as err:
        raise HTTPException(status_code=504, detail="search timed out") from err
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
