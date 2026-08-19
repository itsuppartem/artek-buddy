from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from artek_buddy.contracts.events import ThreadMessage
from artek_buddy.contracts.ids import Id, MemoryScope, RunStatus, SandboxKind


class ComputerMode(str):
    team = "team"
    dedicated = "dedicated"


class Bot(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    workspace_id: Id
    name: str
    title: str
    description: str
    instructions: str
    color: str
    notify_on_finish: bool
    pinned: bool
    archived_at: str | None
    unread: bool
    parent_bot_id: Id | None
    thread_id: Id
    preview: str
    status: str
    computer_mode: Literal["team", "dedicated"]
    cursor_agent_id: str | None = None
    updated_at: str
    created_at: str


class CreateBotInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=4000)
    instructions: str = Field(default="", max_length=20000)
    notify_on_finish: bool = True
    color: str | None = None
    computer_mode: Literal["team", "dedicated"] = "team"


class UpdateBotInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    instructions: str | None = Field(default=None, max_length=20000)
    notify_on_finish: bool | None = None
    color: str | None = None
    pinned: bool | None = None
    unread: bool | None = None
    computer_mode: Literal["team", "dedicated"] | None = None


class BotIdInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id


class SetComputerInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id
    mode: Literal["team", "dedicated"]


class DeleteBotInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None
    delete_memories: bool = False


class Routine(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    bot_id: Id
    name: str
    prompt: str
    cron: str
    timezone: str
    active: bool
    notify: bool
    last_run_at: str | None
    next_run_at: str | None
    created_at: str


class CreateRoutineInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    timezone: str = "UTC"
    notify: bool = True
    active: bool = False


class UpdateRoutineInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
    prompt: str | None = Field(default=None, min_length=1)
    cron: str | None = Field(default=None, min_length=1)
    timezone: str | None = None
    notify: bool | None = None
    active: bool | None = None


class RoutineList(BaseModel):
    routines: list[Routine]


class OkResponse(BaseModel):
    ok: bool = True


class TestRunResult(BaseModel):
    routine_id: Id
    task_id: Id
    run_id: Id
    seq: int


class MemoryDocument(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    scope: MemoryScope
    bot_id: Id | None
    path: str
    content: str
    revision: int
    updated_at: str


class CreateMemoryInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    scope: MemoryScope
    bot_id: Id | None = None
    path: str = "MEMORY.md"
    content: str = ""
    kind: str | None = None


class MemoryUpdateInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    content: str


class MemoryListInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None
    scope: MemoryScope | None = None


class MemoryExportInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None


class MemoryDocumentList(BaseModel):
    documents: list[MemoryDocument]


class MarkdownExport(BaseModel):
    markdown: str


class Connection(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    provider: str
    display_name: str
    status: Literal["pending", "connected", "revoked", "error"]
    capabilities: list[str]
    created_at: str


class ConnectionCatalogItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    slug: str
    name: str
    logo: str | None
    connected: bool
    no_auth: bool


class CapabilityInstall(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    kind: Literal["skill", "plugin", "mcp", "connection"]
    name: str
    source: str
    version: str | None
    digest: str | None
    config: dict[str, Any]
    created_at: str


class Artifact(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    bot_id: Id
    run_id: Id | None
    name: str
    mime_type: str
    size: int
    created_at: str


class ArtifactList(BaseModel):
    artifacts: list[Artifact]


class UsageRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    bot_id: Id | None
    run_id: Id | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    created_at: str


class ComputerStatus(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id
    mode: Literal["team", "dedicated"]
    kind: SandboxKind
    state: Literal["stopped", "booting", "running", "suspended", "error"]
    control_holder: Literal["bot", "user", "none"]
    screen_available: bool
    home_revision: str | None
    busy_bot_name: str | None


class TakeoverResult(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    lease_id: str
    expires_at: str


class ComputerInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ComputerFilesInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    path: str = "/"


class ComputerFileEntry(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    path: str
    kind: str
    size: int = 0
    name: str = ""


class ComputerFileList(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    path: str
    entries: list[ComputerFileEntry]


class ComputerReadFileInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    path: str


class ComputerFileContent(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    path: str
    content: str


class ScreenUrlResult(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    url: str | None = None


class Subagent(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    bot_id: Id
    thread_id: Id
    parent_run_id: Id | None = None
    cursor_agent_id: str | None = None
    index: int
    name: str
    task: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: str | None = None
    thinking: str | None = None
    result: str | None = None
    error: str | None = None
    clarifications: str | None = None
    created_at: str
    updated_at: str


class SteerSubagentInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    text: str = Field(min_length=1)


class SubagentList(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    subagents: list[Subagent]


class Run(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    bot_id: Id
    thread_id: Id
    task_id: Id
    status: RunStatus
    trigger: Literal["user", "routine", "resume", "follow_up", "spawn"]
    model_provider: str | None
    model_id: str | None
    error: str | None
    started_at: str | None
    completed_at: str | None


class ThreadMessagePage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    thread_id: Id
    messages: list[ThreadMessage]
    older_cursor: int | None


class ThreadSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id
    thread_id: Id
    cursor: int
    messages: list[ThreadMessage]
    older_cursor: int | None
    run: Run | None
    computer: ComputerStatus
    subagents: list[Subagent] = Field(default_factory=list)


class ModelCredential(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    provider: str
    label: str
    has_key: bool
    is_default: bool


class DeploymentSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    owner_user_id: Id | None = None
    signups_enabled: bool = True
    signup_allowlist: list[str] = Field(default_factory=list)
    has_deployment_model_credential: bool = False
    default_provider: str | None = None
    default_model: str | None = None
    computer_host: Literal["docker", "host"] | None = "docker"
    can_choose_host_computer: bool = True


class UpdateDeploymentInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    signups_enabled: bool | None = None
    signup_allowlist: list[str] | None = None
    computer_host: Literal["docker", "host"] | None = None


class Me(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    user_id: Id = "usr_owner"
    email: str = "owner@artek.local"
    name: str = "Owner"
    workspace_id: Id = "ws_default"
    is_deployment_owner: bool = True
    needs_model: bool = False
    default_provider: str | None = "cursor"
    default_model: str | None = "grok-4.6"
    computer_host: Literal["docker", "host"] | None = "docker"
    can_choose_host_computer: bool = True


class ExportMemoryItem(BaseModel):
    path: str
    content: str


class ExportRoutineItem(BaseModel):
    name: str
    prompt: str
    cron: str
    timezone: str


class ExportFileItem(BaseModel):
    path: str
    content: str


class ExportBotSlice(BaseModel):
    name: str
    title: str
    description: str
    instructions: str


class ExportManifest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    version: Literal[1] = 1
    exported_at: str
    bot: ExportBotSlice
    memory: list[ExportMemoryItem]
    routines: list[ExportRoutineItem]
    files: list[ExportFileItem]
    history: list[ThreadMessage]


class BotList(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bots: list[Bot]


class ThreadMessagesInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None
    before: int | None = None
    limit: int = 50


class ThreadAttachmentInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1)
    mime_type: str | None = None


class HostedAttachment(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    name: str
    mime_type: str
    size: int
    path: str


class AttachmentList(BaseModel):
    attachments: list[HostedAttachment]


class AttachmentUploadInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    files: list[ThreadAttachmentInput]


class ThreadSendInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    text: str = ""
    trigger: Literal["user", "routine", "resume", "follow_up", "spawn"] = "user"
    reply_to_id: Id | None = None
    attachment_ids: list[Id] = Field(default_factory=list)
    attachments: list[ThreadAttachmentInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def need_text_or_files(self) -> ThreadSendInput:
        if not self.text.strip() and not self.attachment_ids and not self.attachments:
            raise ValueError("text or attachments required")
        return self


class ThreadFollowUpInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None
    text: str = Field(min_length=1)


class ThreadAnswerInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    bot_id: Id | None = None
    run_id: Id
    message_id: Id
    answer: str = Field(min_length=1)


class ConsentAnswerInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    decision: str = Field(min_length=1)


class ConsentFileInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1)
    text: str | None = None
    content_base64: str | None = None


class ConsentJob(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    action_class: str
    status: str = "pending"
    path: str | None = None
    command: str | None = None
    cwd: str | None = None
    kind: str | None = None
    text: str | None = None
    content_base64: str | None = None
    summary: str | None = None
    scope_key: str | None = None


class ConsentResultInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ok: bool = True
    name: str | None = None
    text: str | None = None
    content_base64: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    path: str | None = None
    bytes: int | None = None
    entries: list[dict[str, Any]] | None = None
    error: str | None = None


class ThreadSendResult(BaseModel):
    """Accept a user turn. Returns ids immediately. Follow the thread SSE for the rest."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    task_id: Id
    run_id: Id
    seq: int
    message: ThreadMessage | None = None
    run: Run | None = None
    queued: bool = False


class HealthResponse(BaseModel):
    """GET /health is process liveness. db is additive. No agent identity."""

    ok: bool
    db: bool | None = None


class SessionResponse(BaseModel):
    """Current default Cursor agent plus the bot/thread it is mapped to."""

    agent_id: str
    bot_id: str | None = None
    thread_id: str | None = None


class SessionRequest(BaseModel):
    name: str = "artek-buddy"


class RunRequest(BaseModel):
    """Optional alias for a turn. Prefer ThreadSendInput on threads.send."""

    text: str = Field(min_length=1)
    bot_id: str | None = None


class Device(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Id
    name: str
    platform: str
    created_at: str
    last_seen_at: str | None = None
    revoked_at: str | None = None


class DeviceList(BaseModel):
    devices: list[Device]


class CreateDeviceInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1, max_length=80)
    platform: str = Field(default="linux", max_length=40)
    pairing_code: str | None = Field(default=None, max_length=32)


class DeviceCreated(Device):
    """Mint response. `token` is shown once and never stored in plaintext."""

    token: str


class PairingCode(BaseModel):
    code: str
    expires_at: str
