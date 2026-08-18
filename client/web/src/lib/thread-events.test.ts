import { describe, expect, it } from "vitest";
import type { ComputerStatus, ProductEvent, ThreadMessage, ThreadSnapshot } from "../types";
import {
  isHiddenLiveDraft,
  mergeThreadSnapshot,
  prependThreadMessagePage,
  reduceComputerStatus,
  reduceThreadSnapshot,
} from "./thread-events";

describe("thread event reduction", () => {
  it("prepends older pages in order and removes overlaps", () => {
    const initial = snapshot([message("m-2", [], 2), message("m-3", [], 3)], 2);
    const next = prependThreadMessagePage(initial, {
      threadId: "thread-1",
      messages: [message("m-0", [], 0), message("m-1", [], 1), message("m-2", [], 2)],
      olderCursor: null,
    });
    expect(next?.messages.map((item) => item.id)).toEqual(["m-0", "m-1", "m-2", "m-3"]);
    expect(next?.olderCursor).toBeNull();
  });

  it("does not splice another thread's history into the open chat", () => {
    const initial = snapshot([message("m-2", [], 2)], 2);
    const next = prependThreadMessagePage(initial, {
      threadId: "thread-other",
      messages: [message("leak", [], 0)],
      olderCursor: null,
    });
    expect(next).toBe(initial);
    expect(next?.messages.map((item) => item.id)).toEqual(["m-2"]);
  });

  it("merges a refreshed page with loaded history and drops live drafts", () => {
    const previous = snapshot(
      [
        message("m-0", [], 0),
        message("m-1", [], 1),
        message("progress:live", [{ kind: "progress", text: "draft" }], 9),
      ],
      null,
    );
    const recent = snapshot([message("m-1", [], 1), message("m-2", [], 2)], 1);
    const next = mergeThreadSnapshot(previous, recent, true);
    expect(next.messages.map((item) => item.id)).toEqual(["m-0", "m-1", "m-2"]);
  });

  it("accumulates progress deltas on one live bubble", () => {
    const first = reduceThreadSnapshot(
      snapshot([]),
      event({ type: "thread.progress", seq: 4, payload: { delta: "Hel" } }),
    );
    const second = reduceThreadSnapshot(
      first,
      event({ type: "thread.progress", seq: 5, payload: { delta: "lo" } }),
    );
    expect(second?.cursor).toBe(5);
    expect(second?.messages).toEqual([
      expect.objectContaining({
        id: "progress:run-1",
        blocks: [{ kind: "progress", text: "Hello" }],
      }),
    ]);
  });

  it("accumulates token updates on the stream bubble", () => {
    const first = reduceThreadSnapshot(
      snapshot([]),
      event({ type: "thread.message.updated", seq: 4, payload: { delta: "Hi" } }),
    );
    const second = reduceThreadSnapshot(
      first,
      event({ type: "thread.message.updated", seq: 5, payload: { text: "Hi there", replace: true } }),
    );
    expect(second?.messages[0]).toMatchObject({
      id: "stream:run-1",
      blocks: [{ kind: "progress", text: "Hi there" }],
    });
  });

  it("uses the host snapshot text instead of re-appending a leftover delta", () => {
    const first = reduceThreadSnapshot(
      snapshot([]),
      event({ type: "thread.message.updated", seq: 4, payload: { text: "Hello world" } }),
    );
    const second = reduceThreadSnapshot(
      snapshot([]),
      event({
        type: "thread.message.updated",
        seq: 5,
        payload: { text: "Hello world!", delta: "!" },
      }),
    );
    expect(first?.messages[0]?.blocks).toEqual([{ kind: "progress", text: "Hello world" }]);
    expect(second?.messages[0]?.blocks).toEqual([{ kind: "progress", text: "Hello world!" }]);
  });

  it("keeps the stream bubble when thinking arrives", () => {
    const streamed = reduceThreadSnapshot(
      snapshot([]),
      event({ type: "thread.message.updated", seq: 4, payload: { text: "Hello" } }),
    );
    const next = reduceThreadSnapshot(
      streamed,
      event({ type: "thread.progress", seq: 5, payload: { text: "thinking" } }),
    );
    expect(next?.messages.map((item) => item.id)).toEqual(["stream:run-1", "progress:run-1"]);
    expect(next?.messages[0]?.blocks).toEqual([{ kind: "progress", text: "Hello" }]);
  });

  it("keeps live drafts when a refresh lands during an active run", () => {
    const previous = snapshot(
      [message("stream:live", [{ kind: "progress", text: "Hel" }], 9)],
      null,
    );
    previous.run = {
      id: "run-1",
      botId: "bot-1",
      threadId: "thread-1",
      taskId: "t1",
      status: "running",
      trigger: "user",
      modelProvider: null,
      modelId: null,
      error: null,
      startedAt: "2026-08-17T00:00:00.000Z",
      completedAt: null,
    };
    const recent = snapshot([message("m-1", [{ kind: "text", text: "hi" }], 1)], 1);
    recent.run = previous.run;
    const next = mergeThreadSnapshot(previous, recent, false);
    expect(next.messages.map((item) => item.id)).toEqual(["m-1", "stream:live"]);
    expect(next.messages[1]?.blocks).toEqual([{ kind: "progress", text: "Hel" }]);
  });

  it("replaces live drafts with the durable bot message", () => {
    const initial = snapshot([
      message("progress:live", [{ kind: "progress", text: "draft" }], 8),
      message("stream:live", [{ kind: "progress", text: "partial" }], 9),
    ]);
    const next = reduceThreadSnapshot(
      initial,
      event({
        type: "thread.message.created",
        seq: 10,
        payload: {
          message: {
            id: "msg-1",
            role: "bot",
            seq: 10,
            threadId: "thread-1",
            createdAt: "2026-08-17T00:00:02.000Z",
            blocks: [{ kind: "text", text: "done" }],
          },
        },
      }),
    );
    expect(next?.messages.map((item) => item.id)).toEqual(["msg-1"]);
    expect(next?.messages[0]?.blocks).toEqual([{ kind: "text", text: "done" }]);
  });

  it("replaces a pending ask card with the answered one", () => {
    const initial = snapshot([
      message(
        "ask-1",
        [
          {
            kind: "ask",
            text: "Which city?",
            status: "pending",
            actions: [{ id: "opt_1", label: "Belgrade" }],
          },
        ],
        3,
      ),
    ]);
    const next = reduceThreadSnapshot(
      initial,
      event({
        type: "thread.message.created",
        seq: 4,
        payload: {
          message: {
            id: "ask-1",
            role: "bot",
            seq: 3,
            threadId: "thread-1",
            createdAt: "2026-08-17T00:00:02.000Z",
            blocks: [{ kind: "ask", text: "Which city?", status: "answered", answer: "Belgrade" }],
          },
        },
      }),
    );
    expect(next?.messages).toHaveLength(1);
    expect(next?.messages[0]?.blocks).toEqual([
      { kind: "ask", text: "Which city?", status: "answered", answer: "Belgrade" },
    ]);
  });

  it("treats live stream and thinking drafts as hidden monologue", () => {
    expect(isHiddenLiveDraft(message("stream:run-1", [{ kind: "progress", text: "planning" }]))).toBe(
      true,
    );
    expect(isHiddenLiveDraft(message("progress:run-1", [{ kind: "progress", text: "hmm" }]))).toBe(
      true,
    );
    expect(isHiddenLiveDraft(message("msg-1", [{ kind: "text", text: "done" }]))).toBe(false);
  });

  it("drops leftover stream and progress drafts when run completes", () => {
    const initial = snapshot([
      message("stream:run-1", [{ kind: "progress", text: "partial text" }], 5),
      message("progress:run-1", [{ kind: "progress", text: "thinking" }], 6),
    ]);
    initial.run = {
      id: "run-1",
      botId: "bot-1",
      threadId: "thread-1",
      taskId: "t1",
      status: "running",
      trigger: "user",
      modelProvider: null,
      modelId: null,
      error: null,
      startedAt: "2026-08-17T00:00:00.000Z",
      completedAt: null,
    };
    const next = reduceThreadSnapshot(
      initial,
      event({
        type: "run.completed",
        seq: 7,
        runId: "run-1",
        payload: { run: { id: "run-1", status: "completed" } },
      }),
    );
    expect(next?.messages).toEqual([]);
    expect(next?.run?.status).toBe("completed");
  });

  it("upserts a subagent card with thinking and index", () => {
    const started = reduceThreadSnapshot(
      snapshot([]),
      event({
        type: "thread.subagent",
        seq: 6,
        payload: {
          agentId: "sub_1",
          name: "news",
          task: "find headlines",
          status: "running",
          index: 2,
          thinking: "opening the browser",
          clarifications: "only Hacker News",
        },
      }),
    );
    const done = reduceThreadSnapshot(
      started,
      event({
        type: "thread.subagent",
        seq: 7,
        payload: {
          agent_id: "sub_1",
          name: "news",
          task: "find headlines",
          status: "completed",
          index: 2,
          result: "three headlines",
          clarifications: "only Hacker News",
        },
      }),
    );
    expect(done?.messages).toHaveLength(1);
    expect(done?.messages[0]).toMatchObject({
      id: "subagent:sub_1",
      blocks: [
        expect.objectContaining({
          kind: "subagent",
          agentId: "sub_1",
          status: "completed",
          index: 2,
          result: "three headlines",
          clarifications: "only Hacker News",
        }),
      ],
    });
  });

  it("does not paint raw tool calls in the thread", () => {
    const started = reduceThreadSnapshot(
      snapshot([]),
      event({
        type: "agent.tool.called",
        seq: 3,
        payload: { callId: "c1", name: "shell", status: "running" },
      }),
    );
    const computer = reduceThreadSnapshot(
      started,
      event({
        type: "thread.computer",
        seq: 4,
        payload: { state: "completed", text: "computer_act" },
      }),
    );
    expect(started?.messages).toEqual([]);
    expect(computer?.messages).toEqual([]);
    expect(computer?.cursor).toBe(4);
  });

  it("marks the run running then completed", () => {
    const started = reduceThreadSnapshot(
      snapshot([]),
      event({ type: "run.started", seq: 1, runId: "run-1", payload: { id: "run-1", taskId: "t1" } }),
    );
    expect(started?.run?.status).toBe("running");
    const done = reduceThreadSnapshot(
      started,
      event({ type: "run.completed", seq: 2, runId: "run-1", payload: {} }),
    );
    expect(done?.run?.status).toBe("completed");
  });

  it("keeps the other run live when one run finishes", () => {
    const first = reduceThreadSnapshot(
      snapshot([]),
      event({ type: "run.started", seq: 1, runId: "run-1", payload: { id: "run-1" } }),
    );
    const second = reduceThreadSnapshot(
      first,
      event({ type: "run.started", seq: 2, runId: "run-2", payload: { id: "run-2" } }),
    );
    const streamed = reduceThreadSnapshot(
      second,
      event({
        type: "thread.message.updated",
        seq: 3,
        runId: "run-1",
        payload: { text: "news" },
      }),
    );
    const user = reduceThreadSnapshot(
      streamed,
      event({
        type: "thread.message.created",
        seq: 4,
        runId: "run-2",
        payload: {
          message: {
            id: "msg-user",
            role: "user",
            seq: 4,
            threadId: "thread-1",
            createdAt: "2026-08-17T00:00:02.000Z",
            blocks: [{ kind: "text", text: "sine 100" }],
          },
        },
      }),
    );
    expect(user?.messages.map((item) => item.id)).toEqual(["stream:run-1", "msg-user"]);
    const otherDone = reduceThreadSnapshot(
      user,
      event({ type: "run.completed", seq: 5, runId: "run-1", payload: {} }),
    );
    expect(otherDone?.run?.id).toBe("run-2");
    expect(otherDone?.run?.status).toBe("running");
  });
});

describe("computer event reduction", () => {
  it("applies valid states and ignores unknown ones", () => {
    const running = reduceComputerStatus(
      computer(),
      event({ type: "computer.status", payload: { status: "running" } }),
    );
    const unknown = reduceComputerStatus(
      running,
      event({ type: "computer.status", payload: { status: "destroyed" } }),
    );
    expect(running).toMatchObject({ state: "running", screenAvailable: true });
    expect(unknown).toBe(running);
  });

  it("flips control from takeover events", () => {
    const granted = reduceComputerStatus(
      computer({ controlHolder: "bot" }),
      event({ type: "computer.takeover.granted", payload: {} }),
    );
    const released = reduceComputerStatus(
      granted,
      event({ type: "computer.takeover.released", payload: {} }),
    );
    expect(granted?.controlHolder).toBe("user");
    expect(released?.controlHolder).toBe("bot");
  });
});

function snapshot(messages: ThreadMessage[], olderCursor: number | null = null): ThreadSnapshot {
  return {
    botId: "bot-1",
    threadId: "thread-1",
    cursor: 3,
    messages,
    olderCursor,
    run: null,
    computer: computer(),
  };
}

function computer(overrides: Partial<ComputerStatus> = {}): ComputerStatus {
  return {
    botId: "bot-1",
    mode: "team",
    kind: "fake",
    state: "booting",
    controlHolder: "none",
    screenAvailable: false,
    homeRevision: null,
    busyBotName: null,
    ...overrides,
  };
}

function message(id: string, blocks: ThreadMessage["blocks"], seq = 3): ThreadMessage {
  return {
    id,
    threadId: "thread-1",
    seq,
    role: "bot",
    blocks,
    createdAt: "2026-08-17T00:00:00.000Z",
  };
}

function event(overrides: Partial<ProductEvent>): ProductEvent {
  return {
    id: "event-1",
    workspaceId: "workspace-1",
    threadId: "thread-1",
    botId: "bot-1",
    seq: 4,
    type: "thread.progress",
    runId: "run-1",
    createdAt: "2026-08-17T00:00:01.000Z",
    payload: {},
    ...overrides,
  };
}
