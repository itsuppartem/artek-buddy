import { describe, expect, it, vi } from "vitest";
import { completeOwnerConsent, isAutoOwnerJob, ownerJobHint, ownerReadPath } from "./consent";
import { api } from "../api";
import type { ProductEvent } from "../types";

function event(payload: Record<string, unknown>): ProductEvent {
  return {
    id: "evt_1",
    workspaceId: "ws_1",
    threadId: "th_1",
    botId: "bot_1",
    seq: 1,
    createdAt: "2026-08-19T12:00:00.000Z",
    type: "run.waiting_input",
    payload,
  };
}

describe("ownerJobHint", () => {
  it("reads the path from the ask detail", () => {
    expect(ownerReadPath({ text: "Read a file?", detail: "owner_read: /home/me/notes.txt" })).toBe(
      "/home/me/notes.txt",
    );
    expect(ownerJobHint({ text: "Write a file?", detail: "owner_write: ~/todo.md" })).toEqual({
      kind: "owner_write",
      value: "~/todo.md",
    });
    expect(ownerJobHint({ text: "Run it?", detail: "owner_exec: python3 app.py\ncwd: ~/proj" })).toEqual({
      kind: "owner_exec",
      value: "python3 app.py",
    });
  });

  it("falls back to the question text", () => {
    expect(ownerReadPath({ text: "Read ~/Projects/readme.md from your computer?" })).toBe(
      "~/Projects/readme.md",
    );
  });
});

describe("completeOwnerConsent", () => {
  it("answers the host even when the local job fails", async () => {
    vi.spyOn(api.consents, "get").mockResolvedValue({
      id: "cns_1",
      actionClass: "owner_read",
      status: "pending",
      kind: "list",
      path: "~/Downloads",
    });
    vi.spyOn(api.local, "ownerList").mockRejectedValue(new Error("folder not found"));
    const result = vi.spyOn(api.consents, "uploadResult").mockResolvedValue({ ok: false });
    const answer = vi.spyOn(api.consents, "answer").mockResolvedValue({ ok: true });
    await expect(completeOwnerConsent("cns_1", "once")).rejects.toThrow(/folder not found/);
    expect(result).toHaveBeenCalledWith("cns_1", { ok: false, error: "folder not found" });
    expect(answer).toHaveBeenCalledWith("cns_1", "once");
    vi.restoreAllMocks();
  });

  it("Deny answers the host and does not touch the owner PC", async () => {
    const list = vi.spyOn(api.local, "ownerList");
    const answer = vi.spyOn(api.consents, "answer").mockResolvedValue({ ok: true });
    await completeOwnerConsent("cns_2", "deny");
    expect(list).not.toHaveBeenCalled();
    expect(answer).toHaveBeenCalledWith("cns_2", "deny");
    vi.restoreAllMocks();
  });
});

describe("isAutoOwnerJob", () => {
  it("picks Always-grant owner jobs", () => {
    expect(
      isAutoOwnerJob(event({ auto: true, consentId: "cns_1", actionClass: "owner_exec" })),
    ).toEqual({ consentId: "cns_1" });
    expect(isAutoOwnerJob(event({ consentId: "cns_1", actionClass: "owner_read" }))).toBeNull();
    expect(isAutoOwnerJob(event({ auto: true, consentId: "cns_1", actionClass: "browse" }))).toBeNull();
  });
});
