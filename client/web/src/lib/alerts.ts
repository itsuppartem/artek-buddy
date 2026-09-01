import type { ProductEvent } from "../types";
import { stripMarkdown } from "./markdown";

export type AttentionKind = "replied" | "ask" | "takeover" | "failed";

export type AttentionAlert = {
  kind: AttentionKind;
  occurrenceId: string;
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

const watchBackgroundStatus = new Set(["queued", "leased", "running", "waiting_takeover"]);

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
  occurrenceId: string,
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
    occurrenceId,
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

function finalReplyText(payload: Record<string, unknown>): string | null {
  const message = asRecord(payload.message);
  if (message?.role !== "bot") return null;
  const blocks = message.blocks;
  if (!Array.isArray(blocks)) return null;
  const texts: string[] = [];
  for (const raw of blocks) {
    const block = asRecord(raw);
    if (block?.kind !== "text" || typeof block.text !== "string") continue;
    const text = block.text.trim();
    if (text) texts.push(text);
  }
  return texts.length ? texts.join("\n") : null;
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
    const reply = finalReplyText(event.payload);
    return reply ? makeAlert("replied", event.runId || event.id, botId, botName, reply, at) : null;
  }
  if (event.type === "run.failed") {
    const error = typeof event.payload.error === "string" ? event.payload.error : "";
    return makeAlert("failed", event.runId || event.id, botId, botName, error, at);
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
        ? typeof event.payload.text === "string"
          ? event.payload.text
          : "The bot is waiting for you."
        : "Take control of the computer.";
    return makeAlert(
      event.type === "run.waiting_input" ? "ask" : "takeover",
      event.type === "run.waiting_input" && typeof event.payload.messageId === "string"
        ? event.payload.messageId
        : event.runId || event.id,
      botId,
      botName,
      body,
      at,
    );
  }
  return null;
}

export function attentionFromParkedBot(bot: BotAlertSnapshot): AttentionAlert | null {
  if (bot.status !== "waiting_takeover") return null;
  return makeAlert(
    "takeover",
    bot.updatedAt,
    bot.id,
    bot.name,
    "Take control of the computer.",
    bot.updatedAt,
  );
}

export function parkedAttentionForView(
  bots: BotAlertSnapshot[],
  viewingBotId: string | null,
  dismissed: ReadonlySet<string>,
  openedAtMs?: number,
  freshBotIds?: ReadonlySet<string>,
): AttentionAlert | null {
  let best: AttentionAlert | null = null;
  for (const bot of bots) {
    if (bot.id === viewingBotId) continue;
    if (openedAtMs != null && !freshBotIds?.has(bot.id)) {
      const updated = Date.parse(bot.updatedAt);
      if (Number.isFinite(updated) && updated < openedAtMs) continue;
    }
    const alert = attentionFromParkedBot(bot);
    if (!alert) continue;
    if (dismissed.has(attentionFingerprint(alert))) continue;
    if (!best || shouldReplaceAttention(best, alert)) best = alert;
  }
  return best;
}

export function allowAlert(alert: AttentionAlert, notifyOnFinish: boolean): boolean {
  if (alert.kind === "replied" || alert.kind === "failed") return notifyOnFinish;
  return true;
}

export function attentionFingerprint(
  alert: Pick<AttentionAlert, "botId" | "kind" | "occurrenceId">,
): string {
  return `${alert.botId}:${alert.kind}:${alert.occurrenceId}`;
}

export function shouldConsiderEventForAttention(source: "workspace" | "thread" | "poll"): boolean {
  return source === "workspace";
}

export function desktopWindowFocused(input: {
  gtkActive: boolean | null;
  pageHidden: boolean;
  browserFocused: boolean;
}): boolean {
  if (input.pageHidden) return false;
  if (input.gtkActive === null) return input.browserFocused;
  return input.gtkActive;
}

export function shouldSendDesktopAlert(input: {
  windowFocused: boolean;
  viewingBotId: string | null;
  alertBotId: string;
  pageHidden?: boolean;
}): boolean {
  if (input.viewingBotId !== input.alertBotId) return true;
  return input.windowFocused === false || input.pageHidden === true;
}

export function shouldCountThreadRead(input: {
  viewingBotId: string | null | undefined;
  chatId: string;
  windowFocused: boolean;
  pageHidden: boolean;
}): boolean {
  return input.viewingBotId === input.chatId && input.windowFocused && !input.pageHidden;
}

export function nativeNotifyTag(botId: string): string {
  return `artek-buddy:${botId}`;
}

export function shouldWatchBackgroundBot(
  status: string,
  botId: string,
  viewingBotId: string | null | undefined,
): boolean {
  return botId !== viewingBotId && watchBackgroundStatus.has(status);
}

export function rememberShownAlert(seen: Set<string>, key: string): "show" | "skip" {
  if (seen.has(key)) return "skip";
  seen.add(key);
  return "show";
}

export function parkedTakeoverKey(botId: string): string {
  return `${botId}:takeover:parked`;
}

export function alertKeysToRemember(input: {
  key: string;
  fingerprint: string;
  botId: string;
  kind: AttentionKind;
  surfaced: boolean;
}): string[] {
  if (!input.surfaced) return [];
  const keys = [input.key, input.fingerprint];
  if (input.kind === "takeover") keys.push(parkedTakeoverKey(input.botId));
  return [...new Set(keys.filter(Boolean))];
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

export function shouldStickDismissOnView(
  attention: AttentionAlert | null,
  viewingBotId: string | null | undefined,
  previousViewingBotId: string | null | undefined,
): boolean {
  if (!shouldClearAttentionForView(attention, viewingBotId)) return false;
  return Boolean(previousViewingBotId && previousViewingBotId !== viewingBotId);
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
