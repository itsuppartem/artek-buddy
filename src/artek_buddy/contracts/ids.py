from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field

Id = Annotated[str, Field(min_length=1)]
IsoDate = Annotated[str, Field(min_length=1)]


class Actor(BaseModel):
    user_id: Id
    workspace_id: Id
    email: str
    is_deployment_owner: bool


class RunStatus(str, Enum):
    queued = "queued"
    leased = "leased"
    running = "running"
    waiting_input = "waiting_input"
    waiting_takeover = "waiting_takeover"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EffectStatus(str, Enum):
    intended = "intended"
    completed = "completed"
    failed = "failed"
    ambiguous = "ambiguous"
    reconciled = "reconciled"


class MemoryScope(str, Enum):
    bot = "bot"
    user = "user"


class SandboxKind(str, Enum):
    docker = "docker"
    desktop = "desktop"
    fake = "fake"


# Original Artek Buddy palette.
BOT_COLORS = [
    "#C45C26",
    "#1B6B63",
    "#D4A017",
    "#3D5A80",
    "#8F3D55",
    "#4F7C4A",
    "#B85C38",
]
DEFAULT_BOT_COLOR = BOT_COLORS[0]
