import { describe, expect, it } from "vitest";
import type { Subagent } from "../types";
import { inFlightProgressText } from "./in-flight-status";

function worker(over: Partial<Subagent> & Pick<Subagent, "id" | "status">): Subagent {
  return {
    botId: "b",
    threadId: "t",
    parentRunId: "run1",
    cursorAgentId: null,
    index: 0,
    name: "Worker",
    task: "task",
    progress: null,
    progressRemaining: null,
    progressPostedAt: null,
    progressPostedText: null,
    thinking: null,
    result: null,
    error: null,
    clarifications: null,
    lastActivityAt: "2026-01-01T00:00:00Z",
    activitySeq: 0,
    lastActivityKind: null,
    lastToolName: null,
    toolRunning: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

describe("inFlightProgressText", () => {
  it("is empty until an active worker has a step", () => {
    expect(inFlightProgressText(undefined)).toBe("");
    expect(inFlightProgressText([worker({ id: "s1", status: "running" })])).toBe("");
    expect(
      inFlightProgressText([
        worker({ id: "s1", status: "completed", progress: "commit", progressRemaining: "push" }),
      ]),
    ).toBe("");
  });

  it("formats the latest active worker step", () => {
    expect(
      inFlightProgressText([
        worker({
          id: "old",
          status: "running",
          progress: "clone",
          activitySeq: 1,
        }),
        worker({
          id: "new",
          status: "running",
          progress: "commit",
          progressRemaining: "push MR 76",
          activitySeq: 2,
        }),
      ]),
    ).toBe("Still working: commit. Next: push MR 76.");
  });

  it("ties equal activity seq by last activity then id", () => {
    expect(
      inFlightProgressText([
        worker({
          id: "a",
          status: "running",
          progress: "alpha",
          activitySeq: 4,
          lastActivityAt: "2026-01-01T00:00:01Z",
        }),
        worker({
          id: "b",
          status: "queued",
          progress: "beta",
          activitySeq: 4,
          lastActivityAt: "2026-01-01T00:00:02Z",
        }),
      ]),
    ).toBe("Still working: beta.");
  });
});
