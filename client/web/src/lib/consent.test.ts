import { describe, expect, it } from "vitest";
import type { ProductEvent } from "../types";
import { isAutoOwnerJob, ownerJobHint, ownerReadPath } from "./consent";

function event(over: Partial<ProductEvent> & Pick<ProductEvent, "type">): ProductEvent {
  return {
    id: "e1",
    workspaceId: "w",
    threadId: "t",
    botId: "b",
    seq: 1,
    createdAt: "2026-01-01T00:00:00Z",
    payload: {},
    ...over,
  };
}

describe("ownerJobHint", () => {
  it("parses a detail line", () => {
    expect(
      ownerJobHint({
        text: "Read notes.txt from your computer?",
        detail: "owner_read: ~/notes.txt",
      }),
    ).toEqual({ kind: "owner_read", value: "~/notes.txt" });
  });

  it("falls back to the question text", () => {
    expect(ownerJobHint({ text: "List ~/Downloads on your computer?" })).toEqual({
      kind: "owner_list",
      value: "~/Downloads",
    });
  });

  it("keeps only the first line of an exec command", () => {
    expect(ownerJobHint({ text: "Run this?", detail: "owner_exec: ls\nrm -rf /" })).toEqual({
      kind: "owner_exec",
      value: "ls",
    });
  });
});

describe("ownerReadPath", () => {
  it("returns the path only for owner_read", () => {
    expect(ownerReadPath({ text: "Read notes.txt from your computer?" })).toBe("notes.txt");
    expect(ownerReadPath({ text: "Write notes.txt on your computer?" })).toBeNull();
  });
});

describe("isAutoOwnerJob", () => {
  it("requires auto owner waiting_input with a consent id", () => {
    expect(
      isAutoOwnerJob(
        event({
          type: "run.waiting_input",
          payload: { auto: true, consentId: "c1", actionClass: "owner_read" },
        }),
      ),
    ).toEqual({ consentId: "c1" });
  });

  it("ignores interactive consent", () => {
    expect(
      isAutoOwnerJob(
        event({
          type: "run.waiting_input",
          payload: { consentId: "c1", actionClass: "owner_read" },
        }),
      ),
    ).toBeNull();
  });
});
