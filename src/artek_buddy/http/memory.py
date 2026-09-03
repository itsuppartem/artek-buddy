from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query

from artek_buddy.bus import EventHub
from artek_buddy.contracts import (
    CreateMemoryInput,
    MarkdownExport,
    MemoryDocument,
    MemoryDocumentList,
    MemoryScope,
    MemoryUpdateInput,
    OkResponse,
    ProductEventType,
)
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.memory import (
    MemoryConflict,
    MemoryPathError,
    export_markdown,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.deps import (
    _db_error,
    _require_bot,
    hub,
    require_auth,
    store,
)
from artek_buddy.http.turns import (
    _emit,
    _memory_hub,
)

router = APIRouter()


@router.get("/v1/memory", dependencies=[Depends(require_auth)])
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


@router.post("/v1/memory", dependencies=[Depends(require_auth)])
async def create_memory(
    body: CreateMemoryInput,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> MemoryDocument:
    from artek_buddy.bot_credentials import raise_if_pasted_credential

    raise_if_pasted_credential(body.content)
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
                "scope": document.scope.value
                if hasattr(document.scope, "value")
                else document.scope,
                "revision": document.revision,
            },
        )
    return document


@router.get("/v1/memory/export", dependencies=[Depends(require_auth)])
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


@router.patch("/v1/memory/{document_id}", dependencies=[Depends(require_auth)])
async def update_memory(
    document_id: str,
    body: MemoryUpdateInput,
    history: HistoryStore = Depends(store),
    events: EventHub = Depends(hub),
) -> MemoryDocument:
    from artek_buddy.bot_credentials import raise_if_pasted_credential

    raise_if_pasted_credential(body.content)
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
                    "scope": document.scope.value
                    if hasattr(document.scope, "value")
                    else document.scope,
                    "revision": document.revision,
                },
            )
    return document


@router.delete("/v1/memory/{document_id}", dependencies=[Depends(require_auth)])
async def remove_memory(
    document_id: str,
    history: HistoryStore = Depends(store),
) -> OkResponse:
    try:
        hub = _memory_hub()
        deleted = (
            hub.remove_document(document_id)
            if hub is not None
            else history.delete_memory(document_id)
        )
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    if not deleted:
        raise HTTPException(status_code=404, detail="memory document not found")
    return OkResponse(ok=True)
