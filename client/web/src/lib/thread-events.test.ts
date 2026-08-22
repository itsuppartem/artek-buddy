import { describe, expect, it } from "vitest";
import type { ComputerStatus, ProductEvent, Run, ThreadSnapshot } from "../types";
import {
  isHiddenLiveDraft,
  isLiveMessageId,
  isToolNoise,
  liveMessageId,
  reduceThreadSnapshot,
} from "./thread-events";

function computer(): ComputerStatus {
  return {
    botId: "b",
    mode: "team",
    kind: "fake",
    state: "stopped",
    controlHolder: "bot",
    screenAvailable: false,
    homeRevision: null,
    busyBotName: null,
  };
}

function run(over: Partial<Run> = {}): Run {
  return {
    id: "run1",
    botId: "b",
    threadId: "t",
    taskId: "task",
    status: "running",
    trigger: "user",
    modelProvider: null,
    modelId: null,
    error: null,
    startedAt: "2026-01-01T00:00:00Z",
    completedAt: null,
    ...over,
  };
}

function snap(over: Partial<ThreadSnapshot> = {}): ThreadSnapshot {
  return {
    botId: "b",
    threadId: "t",
    cursor: 1,
    messages: [],
    olderCursor: null,
    run: null,
    computer: computer(),
    ...over,
  };
}

function event(over: Partial<ProductEvent> & Pick<ProductEvent, "type">): ProductEvent {
  return {
    id: "e1",
    workspaceId: "w",
    threadId: "t",
    botId: "b",
    seq: 2,
    createdAt: "2026-01-01T00:00:01Z",
    payload: {},
    runId: "run1",
    ...over,
  };
}

describe("live message ids", () => {
  it("tags streaming drafts so the open chat can hide them", () => {
    expect(liveMessageId("stream", "run1")).toBe("stream:run1");
    expect(isLiveMessageId("progress:run1")).toBe(true);
    expect(
      isHiddenLiveDraft({
        id: "stream:run1",
        threadId: "t",
        seq: 1,
        role: "bot",
        blocks: [{ kind: "progress", text: "…" }],
        runId: "run1",
        createdAt: "2026-01-01T00:00:00Z",
      }),
    ).toBe(true);
  });
});

describe("isToolNoise", () => {
  it("hides empty computer blocks and tool: ids", () => {
    expect(
      isToolNoise({
        id: "tool:1",
        threadId: "t",
        seq: 1,
        role: "bot",
        blocks: [{ kind: "text", text: "hi" }],
        runId: "run1",
        createdAt: "2026-01-01T00:00:00Z",
      }),
    ).toBe(true);
    expect(
      isToolNoise({
        id: "m1",
        threadId: "t",
        seq: 1,
        role: "bot",
        blocks: [{ kind: "computer", state: "running", text: "" }],
        runId: "run1",
        createdAt: "2026-01-01T00:00:00Z",
      }),
    ).toBe(true);
  });
});

describe("reduceThreadSnapshot", () => {
  it("does not let a late complete overwrite a cancelled run", () => {
    const prev = snap({
      run: run({ status: "cancelled" }),
      messages: [
        {
          id: "stream:run1",
          threadId: "t",
          seq: 1,
          role: "bot",
          blocks: [{ kind: "progress", text: "essay" }],
          runId: "run1",
          createdAt: "2026-01-01T00:00:00Z",
        },
      ],
    });
    const next = reduceThreadSnapshot(prev, event({ type: "run.completed" }));
    expect(next?.run?.status).toBe("cancelled");
    expect(next?.messages.map((message) => message.id)).toEqual(["stream:run1"]);
  });
});
