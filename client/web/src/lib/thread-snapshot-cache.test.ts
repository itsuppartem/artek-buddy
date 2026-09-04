import { describe, expect, it } from "vitest";
import type { ComputerStatus, ThreadMessage, ThreadSnapshot } from "../types";
import {
  applyOlderPageForBot,
  applySnapshotForBot,
  createThreadSnapshotCache,
  forgetThread,
  peekThread,
  rememberThread,
  THREAD_SNAPSHOT_CACHE_LIMIT,
  touchThread,
} from "./thread-snapshot-cache";

function computer(botId = "a"): ComputerStatus {
  return {
    botId,
    mode: "team",
    kind: "fake",
    state: "stopped",
    controlHolder: "bot",
    controlLeaseId: null,
    screenAvailable: false,
    homeRevision: null,
    busyBotName: null,
  };
}

function message(id: string, text: string, seq: number, botId = "a"): ThreadMessage {
  return {
    id,
    threadId: `t-${botId}`,
    seq,
    role: "user",
    blocks: [{ kind: "text", text }],
    runId: null,
    createdAt: "2026-01-01T00:00:00Z",
  };
}

function snap(botId: string, texts: string[], over: Partial<ThreadSnapshot> = {}): ThreadSnapshot {
  const messages = texts.map((text, index) => message(`${botId}-${index}`, text, index + 1, botId));
  return {
    botId,
    threadId: `t-${botId}`,
    cursor: messages.length,
    messages,
    olderCursor: "older-1",
    run: null,
    computer: computer(botId),
    ...over,
  };
}

function texts(entry: { snapshot: ThreadSnapshot } | undefined): string[] {
  return (entry?.snapshot.messages ?? []).flatMap((row) =>
    row.blocks.flatMap((block) => ("text" in block && block.text ? [block.text] : [])),
  );
}

describe("thread snapshot cache", () => {
  it("evicts the least recently remembered chat past the bound", () => {
    const cache = createThreadSnapshotCache();
    rememberThread(cache, "a", {
      snapshot: snap("a", ["A"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    rememberThread(cache, "b", {
      snapshot: snap("b", ["B"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    rememberThread(cache, "c", {
      snapshot: snap("c", ["C"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    rememberThread(cache, "d", {
      snapshot: snap("d", ["D"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    expect(THREAD_SNAPSHOT_CACHE_LIMIT).toBe(3);
    expect(peekThread(cache, "a")).toBeUndefined();
    expect(texts(peekThread(cache, "b"))).toEqual(["B"]);
    expect(texts(peekThread(cache, "d"))).toEqual(["D"]);
  });

  it("keeps a touched chat when a newer one is remembered", () => {
    const cache = createThreadSnapshotCache();
    rememberThread(cache, "a", {
      snapshot: snap("a", ["A"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    rememberThread(cache, "b", {
      snapshot: snap("b", ["B"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    rememberThread(cache, "c", {
      snapshot: snap("c", ["C"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    touchThread(cache, "a");
    rememberThread(cache, "d", {
      snapshot: snap("d", ["D"]),
      preserveLoadedHistory: false,
      atStart: false,
    });
    expect(peekThread(cache, "b")).toBeUndefined();
    expect(texts(peekThread(cache, "a"))).toEqual(["A"]);
    expect(texts(peekThread(cache, "c"))).toEqual(["C"]);
    expect(texts(peekThread(cache, "d"))).toEqual(["D"]);
  });

  it("does not store chat B under chat A from a late snapshot", () => {
    const cache = createThreadSnapshotCache();
    applySnapshotForBot(cache, "a", snap("a", ["from A"]));
    const ignored = applySnapshotForBot(cache, "a", snap("b", ["from B"]));
    expect(texts(ignored)).toEqual(["from A"]);
    expect(peekThread(cache, "b")).toBeUndefined();
    applySnapshotForBot(cache, "b", snap("b", ["from B"]));
    expect(texts(peekThread(cache, "a"))).toEqual(["from A"]);
    expect(texts(peekThread(cache, "b"))).toEqual(["from B"]);
  });

  it("keeps an explicit older page across a later latest-50 snapshot", () => {
    const cache = createThreadSnapshotCache();
    applySnapshotForBot(cache, "a", snap("a", ["e2e-old-40"]));
    applyOlderPageForBot(cache, "a", {
      threadId: "t-a",
      messages: [message("old-00", "e2e-old-00", 1)],
      olderCursor: null,
    });
    applySnapshotForBot(cache, "a", snap("a", ["e2e-old-40"]));
    expect(texts(peekThread(cache, "a"))).toEqual(["e2e-old-00", "e2e-old-40"]);
    expect(peekThread(cache, "a")?.atStart).toBe(true);
    expect(peekThread(cache, "a")?.snapshot.olderCursor).toBeNull();
  });

  it("marks a snapshot without an older cursor as the beginning", () => {
    const cache = createThreadSnapshotCache();

    applySnapshotForBot(cache, "a", snap("a", ["first"], { olderCursor: null }));

    expect(peekThread(cache, "a")?.atStart).toBe(true);
  });

  it("ignores an older page that belongs to another thread", () => {
    const cache = createThreadSnapshotCache();
    applySnapshotForBot(cache, "a", snap("a", ["stay"]));
    applyOlderPageForBot(cache, "a", {
      threadId: "t-b",
      messages: [message("other", "leak", 1, "b")],
      olderCursor: null,
    });
    expect(texts(peekThread(cache, "a"))).toEqual(["stay"]);
  });

  it("drops a forgotten chat", () => {
    const cache = createThreadSnapshotCache();
    rememberThread(cache, "a", {
      snapshot: snap("a", ["A"]),
      preserveLoadedHistory: true,
      atStart: true,
    });
    forgetThread(cache, "a");
    expect(peekThread(cache, "a")).toBeUndefined();
  });
});
