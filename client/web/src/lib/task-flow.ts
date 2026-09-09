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
};

const activeExecution = new Set<ExecutionState>(["queued", "running", "waiting"]);
const resultExecution = new Set<ExecutionState>(["completed", "failed", "cancelled"]);

const statusExecution: Record<string, ExecutionState> = {
  queued: "queued",
  leased: "queued",
  running: "running",
  waiting_input: "waiting",
  waiting_takeover: "waiting",
  needs_you: "waiting",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
  idle: "completed",
  sleeping: "completed",
  suspended: "completed",
  done: "completed",
  "": "completed",
};

export function executionFromStatus(status: string): ExecutionState {
  return statusExecution[(status || "").toLocaleLowerCase()] ?? "unknown";
}

export function botTaskStages(bot: TodayBot): BotTaskStage[] {
  const attention = bot.attentionReason ?? "none";
  const execution = bot.executionState ?? executionFromStatus(bot.status);
  const stages: BotTaskStage[] = [];
  if (attention !== "none") stages.push("decision");
  else if (activeExecution.has(execution)) stages.push("working");
  const hasResult = Boolean(bot.resultId) || resultExecution.has(execution);
  if (bot.unread && hasResult && stages[0] === "working") stages.push("ready");
  else if (bot.unread && stages.length === 0) stages.push("ready");
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

export function mergeBotList(current: Bot[], incoming: Bot[]): Bot[] {
  const prev = new Map(current.map((bot) => [bot.id, bot]));
  const seen = new Set<string>();
  const out: Bot[] = [];
  for (const bot of incoming) {
    seen.add(bot.id);
    const old = prev.get(bot.id);
    out.push(old ? applyBotProjection(old, bot) : bot);
  }
  for (const bot of current) {
    if (!seen.has(bot.id)) out.push(bot);
  }
  return out;
}

export function markConnectionLost(bots: Bot[]): Bot[] {
  return bots.map((bot) => ({ ...bot, connectionState: "last_known" as const }));
}
