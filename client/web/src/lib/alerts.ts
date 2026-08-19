import { stripMarkdown } from "./markdown";
import type { ProductEvent } from "../types";

export type AttentionKind = "replied" | "ask" | "takeover" | "failed";

export type AttentionAlert = {
  kind: AttentionKind;
  botId: string;
  title: string;
  body: string;
  urgency: "low" | "normal" | "critical";
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

function makeAlert(kind: AttentionKind, botId: string, botName: string, body: string): AttentionAlert {
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
    if (!block || block.kind !== "ask") continue;
    if (block.status === "answered") continue;
    const text = typeof block.text === "string" ? block.text : "";
    return text || "Choose an option";
  }
  return null;
}

export function attentionFromEvent(event: ProductEvent, botName: string): AttentionAlert | null {
  const botId = event.botId;
  if (event.type === "run.completed") {
    return makeAlert("replied", botId, botName, "");
  }
  if (event.type === "run.failed") {
    const error = typeof event.payload.error === "string" ? event.payload.error : "";
    return makeAlert("failed", botId, botName, error);
  }
  if (event.type === "run.waiting_input" || event.type === "computer.takeover.requested") {
    if (event.type === "run.waiting_input" && (event.payload.auto === true || event.payload.consentId)) {
      return null;
    }
    const body =
      event.type === "run.waiting_input"
        ? "The bot is waiting for you."
        : "Take control of the computer.";
    return makeAlert("takeover", botId, botName, body);
  }
  if (event.type === "thread.ask") {
    const text =
      (typeof event.payload.text === "string" && event.payload.text) ||
      (typeof event.payload.question === "string" && event.payload.question) ||
      "";
    return makeAlert("ask", botId, botName, text);
  }
  if (event.type === "thread.message.created") {
    const ask = pendingAskText(event.payload);
    if (ask) return makeAlert("ask", botId, botName, ask);
  }
  return null;
}

export function attentionFromBotChange(
  prev: BotAlertSnapshot,
  next: BotAlertSnapshot,
): AttentionAlert | null {
  if (prev.id !== next.id) return null;
  const name = next.name;
  if (next.status === "waiting_takeover" && prev.status !== "waiting_takeover") {
    return makeAlert("takeover", next.id, name, "Take control of the computer.");
  }
  if (next.status === "waiting_input" && prev.status !== "waiting_input") {
    return makeAlert("ask", next.id, name, next.preview);
  }
  const leftBusy = busyStatus.has(prev.status) && !busyStatus.has(next.status);
  if (!leftBusy || !next.unread) return null;
  if (next.status === "error") {
    return makeAlert("failed", next.id, name, next.preview);
  }
  return makeAlert("replied", next.id, name, next.preview);
}

export function allowAlert(alert: AttentionAlert, notifyOnFinish: boolean): boolean {
  if (alert.kind === "replied" || alert.kind === "failed") return notifyOnFinish;
  return true;
}

export function shouldSendDesktopAlert(input: {
  windowFocused: boolean;
  viewingBotId: string | null;
  alertBotId: string;
}): boolean {
  if (!input.windowFocused) return true;
  return input.viewingBotId !== input.alertBotId;
}

export function isHistoricalEvent(
  event: Pick<ProductEvent, "createdAt">,
  subscribedAtMs: number,
  skewMs = 2_000,
): boolean {
  const created = Date.parse(event.createdAt);
  if (!Number.isFinite(created)) return false;
  return created < subscribedAtMs - skewMs;
}
