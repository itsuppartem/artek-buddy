import type { ProductEvent } from "../types";
import { stripMarkdown } from "./markdown";

export type AttentionKind = "replied" | "ask" | "takeover" | "failed";

export type AttentionAlert = {
  kind: AttentionKind;
  botId: string;
  title: string;
  body: string;
  urgency: "low" | "normal" | "critical";
  at: string;
};

export type BotAlertSnapshot = {
  id: string;
  name: string;
  status: string;
  unread: boolean;
  preview: string;
  updatedAt: string;
};

const busyStatus = new Set(["queued", "leased", "running", "waiting_input", "waiting_takeover"]);

const urgencyByKind: Record<AttentionKind, AttentionAlert["urgency"]> = {
  replied: "normal",
  ask: "critical",
  takeover: "critical",
  failed: "critical",
};

function clip(text: string, max = 180): string {
  const clean = stripMarkdown(text).replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max - 1).trimEnd()}…`;
}

function makeAlert(
  kind: AttentionKind,
  botId: string,
  botName: string,
  body: string,
  at: string,
): AttentionAlert {
  const name = botName.trim() || "Bot";
  const titles: Record<AttentionKind, string> = {
    replied: `${name} replied`,
    ask: `${name} is asking`,
    takeover: `${name} needs you`,
    failed: `${name} failed`,
  };
  return {
    kind,
    botId,
    title: titles[kind],
    body: clip(body),
    urgency: urgencyByKind[kind],
    at,
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function pendingAskText(payload: Record<string, unknown>): string | null {
  const message = asRecord(payload.message) ?? payload;
  const blocks = message.blocks;
  if (!Array.isArray(blocks)) return null;
  for (const raw of blocks) {
    const block = asRecord(raw);
    if (block?.kind !== "ask") continue;
    if (block.status === "answered") continue;
    const text = typeof block.text === "string" ? block.text : "";
    return text || "Choose an option";
  }
  return null;
}

export function answeredAskBody(event: ProductEvent): string | null {
  if (event.type !== "thread.message.created") return null;
  const message = asRecord(event.payload.message) ?? event.payload;
  const blocks = message.blocks;
  if (!Array.isArray(blocks)) return null;
  for (const raw of blocks) {
    const block = asRecord(raw);
    if (block?.kind !== "ask") continue;
    if (block.status !== "answered") continue;
    const text = typeof block.text === "string" ? block.text : "";
    return clip(text || "Choose an option");
  }
  return null;
}

export function attentionFromEvent(event: ProductEvent, botName: string): AttentionAlert | null {
  const botId = event.botId;
  const at = event.createdAt;
  if (event.type === "run.completed") {
    return makeAlert("replied", botId, botName, "", at);
  }
  if (event.type === "run.failed") {
    const error = typeof event.payload.error === "string" ? event.payload.error : "";
    return makeAlert("failed", botId, botName, error, at);
  }
  if (event.type === "run.waiting_input" || event.type === "computer.takeover.requested") {
    if (
      event.type === "run.waiting_input" &&
      (event.payload.auto === true || event.payload.consentId)
    ) {
      return null;
    }
    const body =
      event.type === "run.waiting_input"
        ? "The bot is waiting for you."
        : "Take control of the computer.";
    return makeAlert("takeover", botId, botName, body, at);
  }
  if (event.type === "thread.ask") {
    const text =
      (typeof event.payload.text === "string" && event.payload.text) ||
      (typeof event.payload.question === "string" && event.payload.question) ||
      "";
    return makeAlert("ask", botId, botName, text, at);
  }
  if (event.type === "thread.message.created") {
    const ask = pendingAskText(event.payload);
    if (ask) return makeAlert("ask", botId, botName, ask, at);
  }
  return null;
}

export function attentionFromBotChange(
  prev: BotAlertSnapshot,
  next: BotAlertSnapshot,
): AttentionAlert | null {
  if (prev.id !== next.id) return null;
  const name = next.name;
  const at = next.updatedAt;
  if (next.status === "waiting_takeover" && prev.status !== "waiting_takeover") {
    return makeAlert("takeover", next.id, name, "Take control of the computer.", at);
  }
  if (next.status === "waiting_input" && prev.status !== "waiting_input") {
    return makeAlert("ask", next.id, name, next.preview, at);
  }
  const leftBusy = busyStatus.has(prev.status) && !busyStatus.has(next.status);
  const becameUnread = next.unread && !prev.unread;
  if (next.status === "error" && (leftBusy || becameUnread)) {
    return makeAlert("failed", next.id, name, next.preview, at);
  }
  if (leftBusy && next.unread) {
    return makeAlert("replied", next.id, name, next.preview, at);
  }
  if (becameUnread && !busyStatus.has(next.status)) {
    return makeAlert("replied", next.id, name, next.preview, at);
  }
  return null;
}

export function allowAlert(alert: AttentionAlert, notifyOnFinish: boolean): boolean {
  if (alert.kind === "replied" || alert.kind === "failed") return notifyOnFinish;
  return true;
}

export function attentionFingerprint(
  alert: Pick<AttentionAlert, "botId" | "kind" | "body">,
): string {
  return `${alert.botId}:${alert.kind}:${alert.body}`;
}

export function shouldSendDesktopAlert(input: {
  windowFocused: boolean;
  viewingBotId: string | null;
  alertBotId: string;
}): boolean {
  if (!input.windowFocused) return true;
  return input.viewingBotId !== input.alertBotId;
}

const urgencyRank: Record<AttentionAlert["urgency"], number> = {
  low: 0,
  normal: 1,
  critical: 2,
};

export function shouldClearAttentionForView(
  attention: AttentionAlert | null,
  viewingBotId: string | null | undefined,
): attention is AttentionAlert {
  return attention != null && viewingBotId === attention.botId;
}

export function shouldReplaceAttention(
  current: AttentionAlert | null,
  next: AttentionAlert,
): boolean {
  if (!current) return true;
  if ((current.kind === "takeover" || current.kind === "ask") && next.kind === "replied") {
    return false;
  }
  const delta = urgencyRank[next.urgency] - urgencyRank[current.urgency];
  if (delta !== 0) return delta > 0;
  const nextAt = Date.parse(next.at);
  const currentAt = Date.parse(current.at);
  if (!Number.isFinite(nextAt) || !Number.isFinite(currentAt)) return true;
  return nextAt >= currentAt;
}

export function isHistoricalEvent(
  event: Pick<ProductEvent, "createdAt">,
  openedAtMs: number,
): boolean {
  const created = Date.parse(event.createdAt);
  if (!Number.isFinite(created)) return false;
  return created < openedAtMs;
}
