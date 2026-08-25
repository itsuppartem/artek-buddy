import type { ThreadMessage } from "../types";

export const OFFLINE_QUEUE_KEY = "artek.offline-queue.v1";
export const OFFLINE_CAPTIONS_KEY = "artek.offline-captions.v1";

export type QueuedAttachment = {
  name: string;
  contentBase64: string;
  mimeType?: string;
};

export type QueuedSend = {
  id: string;
  botId: string;
  text: string;
  replyToId?: string | null;
  attachments?: QueuedAttachment[];
  queuedAt: number;
};

export type OfflineCaption = {
  messageId: string;
  botId: string;
  queuedAt: number;
};

export function shouldQueueSend(kind: "host" | "auth" | "action"): boolean {
  return kind === "host";
}

export function newQueuedId(nowMs = Date.now()): string {
  return `queued:${nowMs}:${Math.random().toString(36).slice(2, 10)}`;
}

export function isQueuedMessageId(id: string): boolean {
  return id.startsWith("queued:");
}

export function enqueueSend(queue: QueuedSend[], item: QueuedSend): QueuedSend[] {
  return [...queue, item];
}

export function removeQueuedSend(queue: QueuedSend[], id: string): QueuedSend[] {
  return queue.filter((item) => item.id !== id);
}

export function queuedForBot(queue: QueuedSend[], botId: string): QueuedSend[] {
  return queue.filter((item) => item.botId === botId);
}

export function parseStoredList<T>(raw: string | null): T[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export function writeStoredList(
  storage: Pick<Storage, "setItem">,
  key: string,
  value: unknown[],
): void {
  storage.setItem(key, JSON.stringify(value));
}

export function userMessageText(message: ThreadMessage): string {
  for (const block of message.blocks) {
    if (block.kind === "text" && block.text) return block.text;
  }
  return "";
}

export function optimisticUserMessage(item: QueuedSend, threadId: string): ThreadMessage {
  return {
    id: item.id,
    threadId,
    seq: 0,
    role: "user",
    createdAt: new Date(item.queuedAt).toISOString(),
    blocks: [{ kind: "text", text: item.text }],
    runId: null,
    replyToId: item.replyToId ?? null,
    replyTo: null,
  };
}

export function mergeQueuedIntoMessages(
  messages: ThreadMessage[],
  queue: QueuedSend[],
  botId: string,
  threadId: string,
): ThreadMessage[] {
  const extra = queuedForBot(queue, botId)
    .filter((item) => !messages.some((message) => message.id === item.id))
    .map((item) => optimisticUserMessage(item, threadId));
  return extra.length ? [...messages, ...extra] : messages;
}

export function captionTargetId(
  item: QueuedSend,
  messages: ThreadMessage[],
  alreadyCaptioned: ReadonlySet<string>,
): string | null {
  const matches = messages.filter((message) => {
    if (message.role !== "user") return false;
    if (isQueuedMessageId(message.id)) return false;
    if (alreadyCaptioned.has(message.id)) return false;
    return userMessageText(message) === item.text;
  });
  return matches.at(-1)?.id ?? null;
}

export function rememberCaption(
  captions: OfflineCaption[],
  caption: OfflineCaption,
): OfflineCaption[] {
  if (captions.some((item) => item.messageId === caption.messageId)) return captions;
  return [...captions, caption];
}

export function captionForMessage(
  captions: OfflineCaption[],
  messageId: string,
): OfflineCaption | undefined {
  return captions.find((item) => item.messageId === messageId);
}

export function formatOfflineCaption(queuedAt: number, now: Date = new Date()): string {
  const time = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(queuedAt));
  void now;
  return `Sent while offline · ${time}`;
}
