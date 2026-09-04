import { describe, expect, it } from "vitest";
import type { ComputerStatus, ProductEvent, Run, ThreadSnapshot } from "../types";
import {
  canAnswerOwnerPrompt,
  isComputerStatusEvent,
  isHiddenLiveDraft,
  isLiveMessageId,
  isRawRunFailedMessage,
  isToolNoise,
  liveMessageId,
  reduceComputerStatus,
  reduceThreadSnapshot,
} from "./thread-events";

function computer(): ComputerStatus {
  return {
    botId: "b",
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

describe("canAnswerOwnerPrompt", () => {
  it("keeps a pending worker consent card answerable after the lead run ends", () => {
    const message = {
      id: "m-consent",
      threadId: "t",
      seq: 1,
      role: "bot" as const,
      blocks: [
        {
          kind: "ask" as const,
          text: "Open example.com?",
          consentId: "c1",
          status: "pending",
        },
      ],
      runId: "sub_worker",
      createdAt: "2026-01-01T00:00:00Z",
    };
    expect(canAnswerOwnerPrompt(message, run({ status: "completed" }))).toBe(true);
    expect(
      canAnswerOwnerPrompt(
        { ...message, blocks: [{ ...message.blocks[0], status: "answered" }] },
        run({ status: "completed" }),
      ),
    ).toBe(false);
  });

  it("keeps an owner question active while the waiting event catches up", () => {
    const message = {
      id: "m-ask",
      threadId: "t",
      seq: 1,
      role: "bot" as const,
      blocks: [{ kind: "ask" as const, text: "Which city?", status: "pending" }],
      runId: "run1",
      createdAt: "2026-01-01T00:00:00Z",
    };
    expect(canAnswerOwnerPrompt(message, run({ status: "waiting_input" }))).toBe(true);
    expect(canAnswerOwnerPrompt(message, run({ status: "running" }))).toBe(true);
    expect(canAnswerOwnerPrompt(message, run({ status: "completed" }))).toBe(false);
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
    expect(
      isToolNoise({
        id: "subagent:s1",
        threadId: "t",
        seq: 1,
        role: "bot",
        blocks: [
          {
            kind: "subagent",
            agentId: "s1",
            name: "Researcher",
            task: "please e2e-slow now",
            status: "running",
          },
        ],
        runId: "run1",
        createdAt: "2026-01-01T00:00:00Z",
      }),
    ).toBe(true);
  });
});

describe("isRawRunFailedMessage", () => {
  it("hides a bot bubble that is only a raw run id", () => {
    expect(
      isRawRunFailedMessage({
        id: "m-fail",
        threadId: "t",
        seq: 1,
        role: "bot",
        blocks: [{ kind: "text", text: "run failed: run-fb7fd73f-32ed-43ed-a22f-a561aab1600a" }],
        runId: "run1",
        createdAt: "2026-01-01T00:00:00Z",
      }),
    ).toBe(true);
    expect(
      isRawRunFailedMessage({
        id: "m-ok",
        threadId: "t",
        seq: 1,
        role: "bot",
        blocks: [{ kind: "text", text: "scripted fail" }],
        runId: "run1",
        createdAt: "2026-01-01T00:00:00Z",
      }),
    ).toBe(false);
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

  it("keeps Working when a model meta arrives without a run id", () => {
    const prev = snap({
      run: run({ status: "running" }),
      messages: [
        {
          id: "meta-old",
          threadId: "t",
          seq: 1,
          role: "bot",
          blocks: [{ kind: "meta", text: "Using scripted · Low · Fast." }],
          createdAt: "2026-01-01T00:00:00Z",
        },
        {
          id: "progress:run1",
          threadId: "t",
          seq: 2,
          role: "bot",
          blocks: [{ kind: "progress", text: "…" }],
          runId: "run1",
          createdAt: "2026-01-01T00:00:01Z",
        },
      ],
    });
    const next = reduceThreadSnapshot(
      prev,
      event({
        type: "thread.message.created",
        runId: "",
        payload: {
          message: {
            id: "meta-new",
            role: "bot",
            seq: 3,
            blocks: [
              {
                kind: "meta",
                text: "Using scripted · High · Fast. This turn keeps going.",
              },
            ],
          },
        },
      }),
    );
    expect(next?.messages.map((message) => message.id)).toEqual([
      "meta-old",
      "progress:run1",
      "meta-new",
    ]);
  });

  it("drops a late stream token after Stop", () => {
    const prev = snap({
      run: run({ status: "cancelled", error: "Stopped." }),
      messages: [],
    });
    const next = reduceThreadSnapshot(
      prev,
      event({
        type: "thread.message.updated",
        payload: { text: "pong", kind: "text", replace: true },
      }),
    );
    expect(next?.run?.status).toBe("cancelled");
    expect(next?.messages).toEqual([]);
  });
});

describe("reduceComputerStatus", () => {
  it("applies computer.status so a stopped tile can become running", () => {
    const next = reduceComputerStatus(
      computer(),
      event({
        type: "computer.status",
        payload: { status: "running", state: "running" },
      }),
    );
    expect(next?.state).toBe("running");
  });

  it("does not treat thread.computer as a pane update", () => {
    expect(isComputerStatusEvent(event({ type: "thread.computer" }))).toBe(false);
  });

  it("Release drops user control so the pane cannot keep You have control", () => {
    const held = reduceComputerStatus(
      computer(),
      event({ type: "computer.takeover.granted", payload: { leaseId: "lease_1" } }),
    );
    expect(held?.controlHolder).toBe("user");
    expect(held?.controlLeaseId).toBe("lease_1");
    const released = reduceComputerStatus(held, event({ type: "computer.takeover.released" }));
    expect(released?.controlHolder).toBe("bot");
    expect(released?.controlLeaseId).toBeNull();
  });
});

describe("thread.subagent", () => {
  it("stores progress on the snapshot so the in-flight slot can reuse it", () => {
    const next = reduceThreadSnapshot(
      snap(),
      event({
        type: "thread.subagent",
        payload: {
          agent_id: "sub_1",
          name: "WorkerProgress",
          task: "please e2e-worker-progress-run",
          status: "running",
          progress: "commit",
          progress_remaining: "push MR 76",
          activity_seq: 3,
          last_activity_at: "2026-01-01T00:00:02Z",
        },
      }),
    );
    expect(next?.subagents).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "sub_1",
          status: "running",
          progress: "commit",
          progressRemaining: "push MR 76",
          activitySeq: 3,
        }),
      ]),
    );
  });
});
