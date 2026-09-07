from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from artek_buddy.contracts.ids import Id

SearchDocumentKind = Literal["message", "memory", "artifact", "bot"]


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    document_kind: SearchDocumentKind
    resource_id: str
    source_id: str
    title: str = ""
    snippet: str = ""


class SearchPage(BaseModel):
    """Authorized hits only. No total — a count would leak hidden rows."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    hits: list[SearchHit] = Field(default_factory=list)
    has_more: bool = False
    next_cursor: str | None = None
