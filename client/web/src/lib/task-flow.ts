import type { Bot } from "../types";

export type BotTaskStage = "decision" | "working" | "ready" | "recent";

export type ExecutionState =
  | "queued"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "unknown";

export type AttentionReason = "approval" | "clarification" | "takeover" | "recovery" | "none";

export type ConnectionState = "live" | "last_known";

export type ResultStatus = "completed" | "failed" | "cancelled";

export type TodayBot = {
  id: string;
  unread: boolean;
  preview: string;
  status: string;
  executionState?: ExecutionState | null;
  attentionReason?: AttentionReason | null;
  connectionState?: ConnectionState | null;
  stateVersion?: number | null;
  resultId?: string | null;
  resultStatus?: ResultStatus | null;
};

const activeExecution = new Set<ExecutionState>(["queued", "running", "waiting"]);

const statusExecution: Record<string, ExecutionState> = {
  queued: "queued",
  leased: "queued",
  running: "running",
  waiting_input: "waiting",
  waiting_takeover: "waiting",
  waiting_recovery: "waiting",
  needs_you: "waiting",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
};

export function executionFromStatus(status: string): ExecutionState {
  const key = (status || "").toLocaleLowerCase();
  if (key === "idle" || key === "sleeping" || key === "suspended" || key === "done" || key === "") {
    return "unknown";
  }
  return statusExecution[key] ?? "unknown";
}

function lastUsableOutcome(bot: TodayBot, execution: ExecutionState): ResultStatus | null {
  if (
    bot.resultStatus === "completed" ||
    bot.resultStatus === "failed" ||
    bot.resultStatus === "cancelled"
  ) {
    return bot.resultStatus;
  }
  if (execution === "completed" || execution === "failed" || execution === "cancelled") {
    return execution;
  }
  return null;
}

export function botTaskStages(bot: TodayBot): BotTaskStage[] {
  const attention = bot.attentionReason ?? "none";
  const execution = bot.executionState ?? executionFromStatus(bot.status);
  const stages: BotTaskStage[] = [];
  if (attention !== "none") stages.push("decision");
  else if (activeExecution.has(execution)) stages.push("working");
  const outcome = lastUsableOutcome(bot, execution);
  const usableUnread = bot.unread && outcome === "completed";
  if (usableUnread && stages[0] === "working") stages.push("ready");
  else if (usableUnread && stages.length === 0) stages.push("ready");
  if (!stages.length) stages.push("recent");
  return stages;
}

export function botTaskStage(bot: TodayBot): BotTaskStage {
  return botTaskStages(bot)[0] ?? "recent";
}

export function applyBotProjection<T extends TodayBot>(current: T, incoming: Partial<T>): T {
  const incomingVer = incoming.stateVersion ?? 0;
  const currentVer = current.stateVersion ?? 0;
  if (incomingVer < currentVer) return current;
  return { ...current, ...incoming };
}

export function mergeBotList(
  current: Bot[],
  incoming: Bot[],
  pendingIds: Iterable<string> = [],
): Bot[] {
  const pending = new Set(pendingIds);
  const prev = new Map(current.map((bot) => [bot.id, bot]));
  const seen = new Set(incoming.map((bot) => bot.id));
  const out = incoming.map((bot) => {
    const old = prev.get(bot.id);
    return old ? applyBotProjection(old, bot) : bot;
  });
  for (const bot of current) {
    if (!seen.has(bot.id) && pending.has(bot.id)) out.push(bot);
  }
  return out;
}

export function markConnectionLost(bots: Bot[]): Bot[] {
  return bots.map((bot) => ({ ...bot, connectionState: "last_known" as const }));
}

export function threadHeaderLabel(
  runStatus: string | undefined,
  attention: AttentionReason | null | undefined,
  title: string | undefined,
  workersBusy = false,
): string {
  if (runStatus === "cancelled") return "Stopped";
  if (runStatus === "failed") return "Failed";
  if (
    runStatus === "waiting_input" ||
    runStatus === "waiting_takeover" ||
    runStatus === "waiting_recovery" ||
    (attention && attention !== "none")
  ) {
    return "Needs you";
  }
  if (runStatus === "running" || runStatus === "queued" || runStatus === "leased" || workersBusy) {
    return "Working";
  }
  if (runStatus === "completed") return "Ready";
  return title?.trim() || "No work yet";
}

export function workSummaryCopy(
  runStatus: string | undefined,
  attention: AttentionReason | null | undefined,
  workersBusy = false,
): { title: string; detail: string; tone: "parked" | "busy" | "failed" | "cancelled" | "done" } {
  if (
    runStatus === "waiting_takeover" ||
    runStatus === "waiting_input" ||
    runStatus === "waiting_recovery" ||
    (attention && attention !== "none")
  ) {
    return {
      title: "Needs your decision",
      detail: "Open the computer or answer the request to continue.",
      tone: "parked",
    };
  }
  if (runStatus === "cancelled") {
    return {
      title: "Stopped by you",
      detail: "The conversation keeps the result and decisions.",
      tone: "cancelled",
    };
  }
  if (runStatus === "failed") {
    return {
      title: "Task failed",
      detail: "The conversation keeps the result and decisions.",
      tone: "failed",
    };
  }
  if (runStatus === "running" || runStatus === "queued" || runStatus === "leased" || workersBusy) {
    return {
      title: "Working on this task",
      detail: "The conversation keeps the result and decisions.",
      tone: "busy",
    };
  }
  if (runStatus === "completed") {
    return {
      title: "Task is complete",
      detail: "The conversation keeps the result and decisions.",
      tone: "done",
    };
  }
  return {
    title: "You can give a first assignment",
    detail: "The conversation keeps the result and decisions.",
    tone: "done",
  };
}

export function workLogLatestFallback(runStatus?: string): string {
  if (runStatus === "cancelled") return "Stopped by you.";
  if (runStatus === "failed") return "This run failed.";
  if (
    runStatus === "waiting_input" ||
    runStatus === "waiting_takeover" ||
    runStatus === "waiting_recovery"
  ) {
    return "Waiting for you.";
  }
  if (runStatus === "running" || runStatus === "queued" || runStatus === "leased") {
    return "Work is still going.";
  }
  if (runStatus === "completed") return "This run completed.";
  if (!runStatus) return "No run in this chat yet.";
  return "Last known action is unavailable.";
}

export function workLogRunStatusLabel(runStatus?: string, current = false): string {
  if (runStatus === "cancelled") return "stopped";
  if (runStatus === "failed") return "failed";
  if (
    runStatus === "waiting_input" ||
    runStatus === "waiting_takeover" ||
    runStatus === "waiting_recovery"
  )
    return "waiting";
  if (runStatus === "running" || runStatus === "queued" || runStatus === "leased") return "running";
  if (runStatus === "completed") return "completed";
  if (current) return "latest";
  return runStatus || "no run";
}
