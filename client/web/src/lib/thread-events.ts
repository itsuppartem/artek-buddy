import type {
  ComputerStatus,
  MessageBlock,
  ProductEvent,
  Subagent,
  ThreadMessage,
  ThreadMessagePage,
  ThreadSnapshot,
} from "../types";

const computerStates = new Set<ComputerStatus["state"]>([
  "stopped",
  "booting",
  "running",
  "suspended",
  "error",
]);

export function mergeThreadSnapshot(
  prev: ThreadSnapshot | null,
  next: ThreadSnapshot,
  preserveLoadedHistory = false,
): ThreadSnapshot {
  if (!prev || prev.threadId !== next.threadId) return mergeSubagentCards(next, prev);
  const seen = new Set(next.messages.map((message) => message.id));
  const older = preserveLoadedHistory
    ? prev.messages.filter((message) => !seen.has(message.id) && !isLive(message.id))
    : [];
  const live = isActiveRun(next.run?.status)
    ? prev.messages.filter((message) => isLive(message.id) && !seen.has(message.id))
    : [];
  if (!older.length && !live.length) return mergeSubagentCards(next, prev);
  return mergeSubagentCards(
    {
      ...next,
      messages: [...older, ...next.messages, ...live].sort((a, b) => a.seq - b.seq),
    },
    prev,
  );
}

export function prependThreadMessagePage(
  prev: ThreadSnapshot | null,
  page: ThreadMessagePage,
): ThreadSnapshot | null {
  if (!prev) return prev;
  if (page.threadId && prev.threadId && page.threadId !== prev.threadId) return prev;
  const seen = new Set(prev.messages.map((message) => message.id));
  const older = page.messages.filter((message) => !seen.has(message.id));
  return {
    ...prev,
    olderCursor: page.olderCursor,
    messages: [...older, ...prev.messages],
  };
}

export function reduceThreadSnapshot(
  prev: ThreadSnapshot | null,
  event: ProductEvent,
): ThreadSnapshot | null {
  if (!prev) return prev;
  if (event.type === "run.started") {
    const run = asRecord(event.payload.run) ?? asRecord(event.payload);
    return {
      ...prev,
      cursor: event.seq,
      run: {
        id: str(run?.id) || event.runId || prev.run?.id || "",
        botId: prev.botId,
        threadId: prev.threadId,
        taskId: str(run?.taskId) || prev.run?.taskId || "",
        status: "running",
        trigger: str(run?.trigger) || "user",
        modelProvider: str(run?.modelProvider) || prev.run?.modelProvider || null,
        modelId: str(run?.modelId) || prev.run?.modelId || null,
        error: null,
        startedAt: str(run?.startedAt) || event.createdAt,
        completedAt: null,
      },
    };
  }
  if (event.type === "run.waiting_input") {
    const run = prev.run;
    if (!run || (event.runId && run.id !== event.runId)) {
      return prev;
    }
    const autoId =
      event.payload.auto === true && typeof event.payload.consentId === "string"
        ? event.payload.consentId
        : prev.pendingAutoConsentId ?? null;
    return {
      ...prev,
      cursor: event.seq,
      run: { ...run, status: "waiting_input" },
      pendingAutoConsentId: autoId,
    };
  }
  if (
    event.type === "run.completed" ||
    event.type === "run.failed" ||
    event.type === "run.cancelled"
  ) {
    if (event.runId && prev.run && prev.run.id !== event.runId) {
      return { ...prev, cursor: event.seq };
    }
    const status =
      event.type === "run.completed"
        ? "completed"
        : event.type === "run.cancelled"
          ? "cancelled"
          : "failed";
    const error = event.payload.error != null ? String(event.payload.error) : prev.run?.error;
    const cleanMessages = prev.messages.filter((message) => !isLiveForRun(message, event.runId));
    return {
      ...prev,
      cursor: event.seq,
      messages: cleanMessages,
      pendingAutoConsentId: null,
      run: prev.run ? { ...prev.run, status, error: error ?? null } : prev.run,
    };
  }
  if (event.type === "thread.progress") {
    const liveId = liveMessageId("progress", event.runId);
    const previous = prev.messages.find((message) => message.id === liveId);
    const previousText = previous?.blocks[0]?.kind === "progress" ? previous.blocks[0].text : "";
    const text = progressText(event.payload, previousText);
    const streaming: ThreadMessage = {
      id: liveId,
      threadId: event.threadId,
      seq: event.seq,
      role: "bot",
      blocks: [{ kind: "progress", text }],
      runId: event.runId,
      createdAt: event.createdAt,
    };
    return { ...prev, cursor: event.seq, messages: replaceLive(prev.messages, streaming) };
  }
  if (event.type === "thread.message.updated") {
    const liveId = liveMessageId("stream", event.runId);
    const text = progressText(event.payload, liveText(prev.messages, liveId));
    const streaming: ThreadMessage = {
      id: liveId,
      threadId: event.threadId,
      seq: event.seq,
      role: "bot",
      blocks: [{ kind: "progress", text }],
      runId: event.runId,
      createdAt: event.createdAt,
    };
    return { ...prev, cursor: event.seq, messages: replaceLive(prev.messages, streaming) };
  }
  if (event.type === "thread.message.created") {
    const raw = asRecord(event.payload.message) ?? event.payload;
    const blocks = normalizeBlocks(raw.blocks) ?? textBlocks(raw);
    if (!blocks.length) return { ...prev, cursor: event.seq };
    const replyTo = asReply(raw.replyTo ?? raw.reply_to);
    const next: ThreadMessage = {
      id: str(raw.id) || event.id,
      threadId: str(raw.threadId) || event.threadId,
      seq: num(raw.seq) || event.seq,
      role: raw.role === "user" || raw.role === "system" ? raw.role : "bot",
      blocks,
      runId: str(raw.runId) || event.runId,
      createdAt: str(raw.createdAt) || event.createdAt,
      replyToId: str(raw.replyToId) || str(raw.reply_to_id) || null,
      replyTo,
    };
    const without = prev.messages.filter((message) => {
      if (message.id === next.id) return false;
      if (next.role === "user") return true;
      return !isLiveForRun(message, next.runId);
    });
    return { ...prev, cursor: event.seq, messages: [...without, next] };
  }
  if (event.type === "thread.meta") {
    const text = str(event.payload.text);
    if (!text) return prev;
    const next: ThreadMessage = {
      id: `meta:${event.id || event.seq}`,
      threadId: event.threadId,
      seq: event.seq,
      role: "bot",
      blocks: [{ kind: "meta", text }],
      runId: event.runId,
      createdAt: event.createdAt,
    };
    return { ...prev, cursor: event.seq, messages: [...prev.messages, next] };
  }
  if (event.type === "thread.subagent") {
    const agentId = str(event.payload.agent_id) || str(event.payload.agentId) || str(event.id);
    const name = str(event.payload.name) || "subagent";
    const task = str(event.payload.task);
    const status = subagentStatus(event.payload.status);
    const progress = event.payload.progress != null ? str(event.payload.progress) : null;
    const thinking = event.payload.thinking != null ? str(event.payload.thinking) : null;
    const result = event.payload.result != null ? str(event.payload.result) : null;
    const index = num(event.payload.index) || null;
    const clarifications =
      event.payload.clarifications != null ? str(event.payload.clarifications) : null;
    const next: ThreadMessage = {
      id: `subagent:${agentId}`,
      threadId: event.threadId,
      seq: event.seq,
      role: "bot",
      blocks: [
        {
          kind: "subagent",
          agentId,
          name,
          task,
          status,
          progress,
          thinking,
          result,
          index,
          clarifications,
        },
      ],
      runId: event.runId,
      createdAt: event.createdAt,
    };
    const without = prev.messages.filter((message) => message.id !== next.id);
    return { ...prev, cursor: event.seq, messages: [...without, next] };
  }
  if (event.type === "bot.spawned") {
    const botId = str(event.payload.bot_id) || str(event.payload.botId) || str(event.id);
    const name = str(event.payload.name) || "bot";
    const title = event.payload.title != null ? str(event.payload.title) : null;
    const next: ThreadMessage = {
      id: `spawn:${botId}`,
      threadId: event.threadId,
      seq: event.seq,
      role: "bot",
      blocks: [{ kind: "child_bot", botId, name, title, status: "created" }],
      runId: event.runId,
      createdAt: event.createdAt,
    };
    const without = prev.messages.filter((message) => message.id !== next.id);
    return { ...prev, cursor: event.seq, messages: [...without, next] };
  }
  if (event.type === "thread.computer" || event.type === "agent.tool.called") {
    return { ...prev, cursor: event.seq };
  }
  return prev;
}

export function reduceComputerStatus(
  prev: ComputerStatus | null,
  event: ProductEvent,
): ComputerStatus | null {
  if (!prev || !isComputerStatusEvent(event)) return prev;
  if (event.type === "computer.takeover.granted") {
    return { ...prev, controlHolder: "user" };
  }
  if (event.type === "computer.takeover.released" || event.type === "computer.takeover.requested") {
    return { ...prev, controlHolder: event.type === "computer.takeover.requested" ? "none" : "bot" };
  }
  const status = event.payload.status ?? event.payload.state;
  const holder = event.payload.controlHolder ?? event.payload.control_holder;
  if (
    !isComputerState(status) &&
    holder !== "user" &&
    holder !== "bot" &&
    holder !== "none" &&
    typeof event.payload.screenAvailable !== "boolean"
  ) {
    return prev;
  }
  const next = { ...prev };
  if (isComputerState(status)) {
    next.state = status;
    next.screenAvailable = status === "running" || status === "booting" || prev.screenAvailable;
  }
  if (holder === "user" || holder === "bot" || holder === "none") {
    next.controlHolder = holder;
  }
  if (typeof event.payload.screenAvailable === "boolean") {
    next.screenAvailable = event.payload.screenAvailable;
  }
  if (event.payload.busyBotName === null || typeof event.payload.busyBotName === "string") {
    next.busyBotName = event.payload.busyBotName as string | null;
  }
  return next;
}

export function isComputerStatusEvent(event: ProductEvent): boolean {
  return (
    event.type === "computer.status" ||
    event.type === "computer.takeover.granted" ||
    event.type === "computer.takeover.released" ||
    event.type === "computer.takeover.requested"
  );
}

function isComputerState(value: unknown): value is ComputerStatus["state"] {
  return computerStates.has(value as ComputerStatus["state"]);
}

const subagentStatuses = new Set<NonNullable<Extract<MessageBlock, { kind: "subagent" }>["status"]>>([
  "queued",
  "running",
  "completed",
  "failed",
  "cancelled",
]);

function subagentStatus(value: unknown): Extract<MessageBlock, { kind: "subagent" }>["status"] {
  const text = str(value);
  return subagentStatuses.has(text as Extract<MessageBlock, { kind: "subagent" }>["status"])
    ? (text as Extract<MessageBlock, { kind: "subagent" }>["status"])
    : "running";
}

export function mergeSubagentCards(
  snap: ThreadSnapshot,
  prev: ThreadSnapshot | null = null,
): ThreadSnapshot {
  const items = snap.subagents ?? [];
  if (!items.length) return snap;
  const prevSeq = new Map(
    (prev?.messages ?? snap.messages)
      .filter((message) => message.id.startsWith("subagent:"))
      .map((message) => [message.id, message.seq]),
  );
  const cards = items
    .slice()
    .sort((left, right) => left.index - right.index)
    .map((item, offset) => subagentMessage(item, prevSeq.get(`subagent:${item.id}`) ?? snap.cursor + offset + 1));
  const rest = snap.messages.filter((message) => !message.id.startsWith("subagent:"));
  return { ...snap, messages: [...rest, ...cards].sort((left, right) => left.seq - right.seq) };
}

function subagentMessage(item: Subagent, seq: number): ThreadMessage {
  return {
    id: `subagent:${item.id}`,
    threadId: item.threadId || "",
    seq,
    role: "bot",
    blocks: [
      {
        kind: "subagent",
        agentId: item.id,
        name: item.name,
        task: item.task,
        status: item.status,
        progress: item.progress ?? null,
        thinking: item.thinking ?? null,
        result: item.result ?? null,
        index: item.index,
        clarifications: item.clarifications ?? null,
      },
    ],
    runId: item.parentRunId,
    createdAt: item.createdAt,
  };
}

function isActiveRun(status: string | undefined): boolean {
  return (
    status === "queued" ||
    status === "leased" ||
    status === "running" ||
    status === "waiting_input" ||
    status === "waiting_takeover"
  );
}

export function liveMessageId(kind: "progress" | "stream", runId?: string | null): string {
  return runId ? `${kind}:${runId}` : `${kind}:live`;
}

export function isLiveMessageId(id: string): boolean {
  return id.startsWith("progress:") || id.startsWith("stream:");
}

export function isHiddenLiveDraft(message: ThreadMessage): boolean {
  return isLiveMessageId(message.id);
}

export function isToolNoise(message: ThreadMessage): boolean {
  if (message.id.startsWith("tool:") || message.id.startsWith("comp:")) return true;
  return message.blocks.length > 0 && message.blocks.every((block) => block.kind === "computer");
}

function isLive(id: string): boolean {
  return isLiveMessageId(id);
}

function isLiveForRun(message: ThreadMessage, runId?: string | null): boolean {
  if (!isLiveMessageId(message.id)) return false;
  if (!runId) return true;
  if (message.runId && message.runId === runId) return true;
  if (message.id === `stream:${runId}` || message.id === `progress:${runId}`) return true;
  if (
    (message.id === "stream:live" || message.id === "progress:live") &&
    (!message.runId || message.runId === runId)
  ) {
    return true;
  }
  return false;
}

function asReply(value: unknown): ThreadMessage["replyTo"] {
  const raw = asRecord(value);
  if (!raw) return null;
  const id = str(raw.id);
  const excerpt = str(raw.excerpt);
  if (!id || !excerpt) return null;
  const role = raw.role === "user" || raw.role === "system" ? raw.role : "bot";
  return { id, role, excerpt };
}

function replaceLive(messages: ThreadMessage[], next: ThreadMessage): ThreadMessage[] {
  return [...messages.filter((message) => message.id !== next.id), next];
}

function liveText(messages: ThreadMessage[], id: string): string {
  const found = messages.find((message) => message.id === id);
  const block = found?.blocks[0];
  return block && "text" in block ? block.text : "";
}

function progressText(payload: Record<string, unknown>, previous: string): string {
  if (payload.text != null && payload.text !== "") {
    const incoming = String(payload.text);
    if (incoming.startsWith(previous) || previous.startsWith(incoming)) {
      return incoming.length >= previous.length ? incoming : previous;
    }
    if (payload.replace) return incoming;
    return incoming.length >= previous.length ? incoming : previous;
  }
  return previous + String(payload.delta ?? "");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function num(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function normalizeBlocks(value: unknown): MessageBlock[] | null {
  if (!Array.isArray(value)) return null;
  return value.filter((block) => block && typeof block === "object") as MessageBlock[];
}

function textBlocks(raw: Record<string, unknown>): MessageBlock[] {
  const text = str(raw.text);
  return text ? [{ kind: "text", text }] : [];
}
