import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
import type { ProductEvent } from "../types";
import {
  fulfillOwnerJob,
  isAutoOwnerJob,
  ownerJobHint,
  ownerReadPath,
  shouldAutoFulfillOwnerJob,
} from "./consent";

afterEach(() => {
  vi.restoreAllMocks();
});

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

describe("shouldAutoFulfillOwnerJob", () => {
  it("leaves auto owner jobs for the desktop client on the host page", () => {
    expect(shouldAutoFulfillOwnerJob("host")).toBe(false);
    expect(shouldAutoFulfillOwnerJob("desktop")).toBe(true);
  });
});

describe("fulfillOwnerJob", () => {
  it("stands down without a result when another client claimed the job", async () => {
    vi.spyOn(api.consents, "get").mockResolvedValue({
      id: "c1",
      actionClass: "owner_read",
      jobStatus: "acknowledged",
      path: "notes.txt",
      status: "pending",
    });
    vi.spyOn(api.consents, "ack").mockRejectedValue(new ApiError("owner job is not queued", 409));
    const read = vi.spyOn(api.local, "ownerRead");
    const upload = vi.spyOn(api.consents, "uploadFile");

    await expect(fulfillOwnerJob("c1")).resolves.toBeUndefined();

    expect(read).not.toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();
  });

  it("returns the ACK claim with the owner's result", async () => {
    vi.spyOn(api.consents, "get").mockResolvedValue({
      id: "c1",
      actionClass: "owner_exec",
      jobStatus: "queued",
      command: "pwd",
      status: "pending",
    });
    vi.spyOn(api.consents, "ack").mockResolvedValue({ ok: true, claim: "claim-1" });
    vi.spyOn(api.local, "ownerExec").mockResolvedValue({
      ok: true,
      stdout: "/home/owner",
      stderr: "",
      exitCode: 0,
    });
    const upload = vi.spyOn(api.consents, "uploadResult").mockResolvedValue({ ok: true });

    await fulfillOwnerJob("c1");

    expect(upload).toHaveBeenCalledWith("c1", {
      ok: true,
      stdout: "/home/owner",
      stderr: "",
      exitCode: 0,
      error: undefined,
      claim: "claim-1",
    });
  });

  it("reports a real winning-client failure with its claim", async () => {
    vi.spyOn(api.consents, "get").mockResolvedValue({
      id: "c1",
      actionClass: "owner_exec",
      jobStatus: "queued",
      command: "pwd",
      status: "pending",
    });
    vi.spyOn(api.consents, "ack").mockResolvedValue({ ok: true, claim: "claim-1" });
    vi.spyOn(api.local, "ownerExec").mockRejectedValue(new Error("local RPC failed"));
    const upload = vi.spyOn(api.consents, "uploadResult").mockResolvedValue({ ok: true });

    await expect(fulfillOwnerJob("c1")).rejects.toThrow("local RPC failed");

    expect(upload).toHaveBeenCalledWith("c1", {
      ok: false,
      error: "local RPC failed",
      claim: "claim-1",
    });
  });
});
