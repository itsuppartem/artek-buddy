import { describe, expect, it } from "vitest";
import type { ThreadMessage } from "../types";
import {
  captionForMessage,
  captionTargetId,
  enqueueSend,
  formatOfflineCaption,
  mergeQueuedIntoMessages,
  newQueuedId,
  type OfflineCaption,
  parseStoredList,
  type QueuedSend,
  rememberCaption,
  removeQueuedSend,
  shouldQueueSend,
} from "./offline-queue";

function user(over: Partial<ThreadMessage> & Pick<ThreadMessage, "id" | "blocks">): ThreadMessage {
  return {
    threadId: "t",
    seq: 1,
    role: "user",
    createdAt: "2026-08-25T08:00:00Z",
    runId: null,
    replyToId: null,
    replyTo: null,
    ...over,
  };
}

function queued(over: Partial<QueuedSend> = {}): QueuedSend {
  return {
    id: "queued:1:a",
    botId: "bot-a",
    text: "hello while down",
    queuedAt: Date.parse("2026-08-25T08:32:00Z"),
    ...over,
  };
}

describe("shouldQueueSend", () => {
  it("queues only when the host cannot be reached", () => {
    expect(shouldQueueSend("host")).toBe(true);
    expect(shouldQueueSend("auth")).toBe(false);
    expect(shouldQueueSend("action")).toBe(false);
  });
});

describe("offline queue order", () => {
  it("keeps FIFO across chats so flush is in send order", () => {
    const first = queued({ id: "queued:1:a", botId: "bot-a", text: "one" });
    const second = queued({ id: "queued:2:b", botId: "bot-b", text: "two" });
    const queue = enqueueSend(enqueueSend([], first), second);
    expect(queue.map((item) => item.text)).toEqual(["one", "two"]);
    expect(removeQueuedSend(queue, first.id).map((item) => item.text)).toEqual(["two"]);
  });

  it("does not drop another chat's items when one id is removed", () => {
    const keep = queued({ id: "queued:2:b", botId: "bot-b", text: "stay" });
    const queue = enqueueSend(enqueueSend([], queued()), keep);
    expect(removeQueuedSend(queue, "queued:1:a")).toEqual([keep]);
  });
});

describe("mergeQueuedIntoMessages", () => {
  it("shows a user bubble for a queued send on that chat only", () => {
    const item = queued();
    const merged = mergeQueuedIntoMessages([], [item], "bot-a", "t");
    expect(merged).toHaveLength(1);
    expect(merged[0]?.role).toBe("user");
    expect(merged[0]?.blocks[0]).toEqual({ kind: "text", text: "hello while down" });
    expect(mergeQueuedIntoMessages([], [item], "bot-b", "t")).toEqual([]);
  });
});

describe("captions after flush", () => {
  it("binds the caption to the host user message, not the local bubble", () => {
    const item = queued();
    const server = user({
      id: "msg_1",
      blocks: [{ kind: "text", text: item.text }],
    });
    expect(captionTargetId(item, [server], new Set())).toBe("msg_1");
    expect(captionTargetId(item, [optimistic(item)], new Set())).toBeNull();
  });

  it("does not reuse a caption already on an earlier same-text send", () => {
    const item = queued();
    const first = user({ id: "msg_old", blocks: [{ kind: "text", text: item.text }] });
    const second = user({ id: "msg_new", blocks: [{ kind: "text", text: item.text }] });
    expect(captionTargetId(item, [first, second], new Set(["msg_old"]))).toBe("msg_new");
  });

  it("formats a local-time caption and remembers it by message id", () => {
    const queuedAt = Date.parse("2026-08-25T08:32:00Z");
    const text = formatOfflineCaption(
      queuedAt,
      new Date("2026-08-25T08:40:00Z"),
      "Europe/Belgrade",
    );
    expect(text.startsWith("Sent while offline · ")).toBe(true);
    expect(text).toMatch(/10:32/);
    expect(text).not.toMatch(/08:32/);
    const captions = rememberCaption([], { messageId: "msg_1", botId: "bot-a", queuedAt });
    expect(captionForMessage(captions, "msg_1")?.queuedAt).toBe(queuedAt);
    expect(rememberCaption(captions, { messageId: "msg_1", botId: "bot-a", queuedAt })).toEqual(
      captions,
    );
  });
});

describe("persist without secrets", () => {
  it("round-trips the queue and treats junk as empty", () => {
    const item = queued();
    const raw = JSON.stringify([item]);
    expect(parseStoredList<QueuedSend>(raw)).toEqual([item]);
    expect(parseStoredList<OfflineCaption>("not-json")).toEqual([]);
    expect(parseStoredList<QueuedSend>(null)).toEqual([]);
  });

  it("minted ids stay local and never look like a host token", () => {
    const id = newQueuedId(1_000);
    expect(id.startsWith("queued:")).toBe(true);
    expect(id.includes("dev_")).toBe(false);
    expect(id.includes("token")).toBe(false);
  });
});

function optimistic(item: QueuedSend): ThreadMessage {
  return user({
    id: item.id,
    blocks: [{ kind: "text", text: item.text }],
  });
}
