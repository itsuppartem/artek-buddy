from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from artek_buddy.contracts.ids import Id

AutomationRunState = Literal[
    "queued",
    "running",
    "waiting_for_approval",
    "succeeded",
    "failed",
    "cancelled",
]


class FireRoutineInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    trigger_event_id: str | None = Field(default=None, max_length=80)


class AutomationRun(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    automation_id: Id
    routine_id: Id
    definition_version: int
    trigger_kind: str
    trigger_event_id: str
    state: AutomationRunState
    snapshot: dict[str, Any] = Field(default_factory=dict)
    thread_run_id: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class AutomationRunList(BaseModel):
    runs: list[AutomationRun] = Field(default_factory=list)


class AutomationDryRun(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    snapshot: dict[str, Any]
    dangerous_tools: bool = False
