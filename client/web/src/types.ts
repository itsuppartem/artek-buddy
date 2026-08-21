export type ComputerMode = "team" | "dedicated";

export type RunStatus =
  | "queued"
  | "leased"
  | "running"
  | "waiting_input"
  | "waiting_takeover"
  | "completed"
  | "failed"
  | "cancelled";

export type Bot = {
  id: string;
  workspaceId: string;
  name: string;
  title: string;
  description: string;
  instructions: string;
  color: string;
  notifyOnFinish: boolean;
  pinned: boolean;
  archivedAt: string | null;
  unread: boolean;
  parentBotId: string | null;
  threadId: string;
  preview: string;
  status: string;
  computerMode: ComputerMode;
  updatedAt: string;
  createdAt: string;
};

export type ComputerStatus = {
  botId: string;
  mode: ComputerMode;
  kind: "docker" | "desktop" | "fake";
  state: "stopped" | "booting" | "running" | "suspended" | "error";
  controlHolder: "bot" | "user" | "none";
  screenAvailable: boolean;
  homeRevision: string | null;
  busyBotName: string | null;
};

export type ComputerFileEntry = {
  path: string;
  name: string;
  kind: "dir" | "file" | string;
  size: number;
};

export type ComputerFileList = {
  path: string;
  entries: ComputerFileEntry[];
};

export type Run = {
  id: string;
  botId: string;
  threadId: string;
  taskId: string;
  status: RunStatus;
  trigger: string;
  modelProvider: string | null;
  modelId: string | null;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
};

export type MessageBlock =
  | { kind: "text"; text: string }
  | { kind: "card"; lines: { k: string; v: string }[] }
  | {
      kind: "ask";
      text: string;
      detail?: string | null;
      status?: "pending" | "answered" | null;
      answer?: string | null;
      actions?: { id: string; label: string }[] | null;
      consentId?: string | null;
    }
  | { kind: "computer"; state: string; text: string }
  | { kind: "meta"; text: string }
  | { kind: "progress"; text: string }
  | {
      kind: "subagent";
      agentId: string;
      name: string;
      task: string;
      status: "queued" | "running" | "completed" | "failed" | "cancelled";
      progress?: string | null;
      thinking?: string | null;
      result?: string | null;
      index?: number | null;
      clarifications?: string | null;
    }
  | {
      kind: "child_bot";
      botId: string;
      name: string;
      title?: string | null;
      status: "created" | "archived" | "deleted";
    }
  | {
      kind: "file";
      artifactId: string;
      name: string;
      mimeType: string;
      size: number;
    };

export type MessageReply = {
  id: string;
  role: "user" | "bot" | "system";
  excerpt: string;
};

export type ThreadMessage = {
  id: string;
  threadId: string;
  seq: number;
  role: "user" | "bot" | "system";
  blocks: MessageBlock[];
  createdAt: string;
  runId?: string | null;
  replyToId?: string | null;
  replyTo?: MessageReply | null;
};

export type Subagent = {
  id: string;
  botId: string;
  threadId: string;
  parentRunId?: string | null;
  cursorAgentId?: string | null;
  index: number;
  name: string;
  task: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress?: string | null;
  thinking?: string | null;
  result?: string | null;
  error?: string | null;
  clarifications?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ThreadSnapshot = {
  botId: string;
  threadId: string;
  cursor: number;
  messages: ThreadMessage[];
  olderCursor: number | null;
  run: Run | null;
  computer: ComputerStatus;
  subagents?: Subagent[];
  pendingAutoConsentId?: string | null;
};

export type ThreadMessagePage = {
  threadId: string;
  messages: ThreadMessage[];
  olderCursor: number | null;
};

export type MemoryScope = "bot" | "user";

export type MemoryDocument = {
  id: string;
  scope: MemoryScope;
  botId: string | null;
  path: string;
  content: string;
  revision: number;
  updatedAt: string;
};

export type Routine = {
  id: string;
  botId: string;
  name: string;
  prompt: string;
  cron: string;
  timezone: string;
  active: boolean;
  notify: boolean;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
};

export type ThreadSendResult = {
  taskId: string;
  runId: string;
  seq: number;
  message?: ThreadMessage | null;
  run?: Run | null;
  queued?: boolean;
};

export type ProductEvent = {
  id: string;
  workspaceId: string;
  threadId: string;
  botId: string;
  seq: number;
  type: string;
  createdAt: string;
  payload: Record<string, unknown>;
  runId?: string | null;
};

export type DesktopBridge = {
  platform: "linux" | "darwin" | "win32";
  window: {
    close: () => void;
    minimize: () => void;
    toggleMaximize: () => void;
  };
};

declare global {
  interface Window {
    artekDesktop?: DesktopBridge;
  }
}
