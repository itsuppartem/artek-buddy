from __future__ import annotations

from fastapi import APIRouter, Depends

from artek_buddy.contracts import SkillBookList
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, _require_bot, require_auth, store

router = APIRouter()


@router.get("/v1/bots/{bot_id}/books", dependencies=[Depends(require_auth)])
async def list_books(bot_id: str, history: HistoryStore = Depends(store)) -> SkillBookList:
    try:
        _require_bot(history, bot_id)
        books = history.list_skill_books(bot_id)
        return SkillBookList(books=[book.model_copy(update={"body": None}) for book in books])
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
