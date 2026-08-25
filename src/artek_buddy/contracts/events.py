from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from artek_buddy.contracts.ids import Id


class ProductEventType(str, Enum):
    THREAD_MESSAGE_CREATED = "thread.message.created"
    THREAD_MESSAGE_UPDATED = "thread.message.updated"
    THREAD_REPLAY_GAP = "thread.replay.gap"
    THREAD_PROGRESS = "thread.progress"
    THREAD_ARTIFACT = "thread.artifact"
    THREAD_ASK = "thread.ask"
    THREAD_CHOICE = "thread.choice"
    THREAD_META = "thread.meta"
    THREAD_COMPUTER = "thread.computer"
    THREAD_SUBAGENT = "thread.subagent"
    RUN_STARTED = "run.started"
    RUN_CHECKPOINTED = "run.checkpointed"
    RUN_WAITING_INPUT = "run.waiting_input"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    COMPUTER_STATUS = "computer.status"
    COMPUTER_TAKEOVER_REQUESTED = "computer.takeover.requested"
    COMPUTER_TAKEOVER_GRANTED = "computer.takeover.granted"
    COMPUTER_TAKEOVER_RELEASED = "computer.takeover.released"
    MEMORY_REVISED = "memory.revised"
    ROUTINE_CREATED = "routine.created"
    ROUTINE_UPDATED = "routine.updated"
    ROUTINE_FIRED = "routine.fired"
    EFFECT_RECORDED = "effect.recorded"
    AGENT_TOOL_CALLED = "agent.tool.called"
    EFFECT_RECONCILED = "effect.reconciled"
    USAGE_RECORDED = "usage.recorded"
    BOT_SPAWNED = "bot.spawned"
    BOT_ARCHIVED = "bot.archived"
    BOT_DELETED = "bot.deleted"


class MessageRole(str, Enum):
    user = "user"
    bot = "bot"
    system = "system"


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    text: str


class CardLine(BaseModel):
    k: str
    v: str


class CardBlock(BaseModel):
    kind: Literal["card"] = "card"
    lines: list[CardLine]


class AskAction(BaseModel):
    id: str
    label: str


class AskBlock(BaseModel):
    kind: Literal["ask"] = "ask"
    text: str
    detail: str | None = None
    status: Literal["pending", "answered"] | None = None
    answer: str | None = None
    actions: list[AskAction] | None = None
    consent_id: str | None = None


class ChoiceOption(BaseModel):
    id: str
    letter: str
    label: str


class ChoiceBlock(BaseModel):
    kind: Literal["choice"] = "choice"
    question: str
    subtitle: str | None = None
    options: list[ChoiceOption]


class ConnectBlock(BaseModel):
    kind: Literal["connect"] = "connect"
    name: str
    initial: str
    color: str
    status: Literal["pending", "connected"]


class ComputerBlock(BaseModel):
    kind: Literal["computer"] = "computer"
    state: str
    text: str


class PluginBlock(BaseModel):
    kind: Literal["plugin"] = "plugin"
    name: str
    text: str


class MetaBlock(BaseModel):
    kind: Literal["meta"] = "meta"
    text: str


class ProgressBlock(BaseModel):
    kind: Literal["progress"] = "progress"
    text: str


class SubagentBlock(BaseModel):
    kind: Literal["subagent"] = "subagent"
    agent_id: str
    name: str
    task: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: str | None = None
    thinking: str | None = None
    result: str | None = None
    index: int | None = None
    clarifications: str | None = None


class ChildBotBlock(BaseModel):
    kind: Literal["child_bot"] = "child_bot"
    bot_id: str
    name: str
    title: str | None = None
    status: Literal["created", "archived", "deleted"]


class FileBlock(BaseModel):
    kind: Literal["file"] = "file"
    artifact_id: str
    name: str
    mime_type: str
    size: int


MessageBlock = Annotated[
    TextBlock
    | CardBlock
    | AskBlock
    | ChoiceBlock
    | ConnectBlock
    | ComputerBlock
    | PluginBlock
    | MetaBlock
    | ProgressBlock
    | SubagentBlock
    | ChildBotBlock
    | FileBlock,
    Field(discriminator="kind"),
]


class ProductEvent(BaseModel):
    id: Id
    workspace_id: Id
    thread_id: Id
    bot_id: Id
    seq: int = Field(ge=0)
    type: ProductEventType
    created_at: str
    payload: dict[str, Any]
    run_id: Id | None = None


class MessageReplyRef(BaseModel):
    id: Id
    role: MessageRole
    excerpt: str


class ThreadMessage(BaseModel):
    id: Id
    thread_id: Id
    seq: int = Field(ge=0)
    role: MessageRole
    blocks: list[MessageBlock]
    created_at: str
    run_id: Id | None = None
    reply_to_id: Id | None = None
    reply_to: MessageReplyRef | None = None
