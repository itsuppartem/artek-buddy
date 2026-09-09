import { describe, expect, it } from "vitest";
import type { Bot } from "../types";
import {
  applyBotProjection,
  botTaskStage,
  botTaskStages,
  markConnectionLost,
  mergeBotList,
} from "./task-flow";

function bot(partial: Partial<Bot> & Pick<Bot, "id">): Bot {
  return {
    color: "#2864dc",
    name: "Bot",
    title: "",
    description: "",
    instructions: "",
    preview: "",
    unread: false,
    pinned: false,
    status: "idle",
    ...partial,
  } as Bot;
}

describe("task-first routing", () => {
  it("groups by host attention and execution, not preview words", () => {
    expect(
      botTaskStage({
        id: "a",
        status: "idle",
        unread: true,
        preview: "No questions remain",
        attentionReason: "none",
        executionState: "completed",
      }),
    ).toBe("ready");
    expect(
      botTaskStage({
        id: "b",
        status: "idle",
        unread: true,
        preview: "Needs approval to send",
        attentionReason: "none",
        executionState: "completed",
      }),
    ).toBe("ready");
    expect(
      botTaskStage({
        id: "c",
        status: "waiting_input",
        unread: false,
        preview: "Choose a delivery window",
        attentionReason: "approval",
        executionState: "waiting",
      }),
    ).toBe("decision");
    expect(
      botTaskStage({
        id: "d",
        status: "running",
        unread: false,
        preview: "Reading source 3",
        attentionReason: "none",
        executionState: "running",
      }),
    ).toBe("working");
    expect(
      botTaskStage({
        id: "e",
        status: "idle",
        unread: false,
        preview: "Sleeping",
        attentionReason: "none",
        executionState: "completed",
      }),
    ).toBe("recent");
  });

  it("does not treat an unknown status as working", () => {
    expect(
      botTaskStage({
        id: "x",
        status: "working",
        unread: false,
        preview: "mystery",
        attentionReason: "none",
        executionState: "unknown",
      }),
    ).toBe("recent");
  });

  it("keeps a previous unread result listed while new work runs", () => {
    expect(
      botTaskStages({
        id: "helper",
        status: "running",
        unread: true,
        preview: "No questions remain",
        attentionReason: "none",
        executionState: "running",
        resultId: "run_old",
      }),
    ).toEqual(["working", "ready"]);
  });

  it("ignores a late snapshot with an older state version", () => {
    const current = bot({
      id: "mail",
      attentionReason: "none",
      executionState: "running",
      stateVersion: 12,
      pendingConsentId: null,
    });
    const merged = applyBotProjection(current, {
      attentionReason: "approval",
      executionState: "waiting",
      stateVersion: 9,
      pendingConsentId: "cns_old",
    });
    expect(merged.attentionReason).toBe("none");
    expect(merged.executionState).toBe("running");
    expect(merged.pendingConsentId).toBeNull();
  });

  it("does not mark execution failed when the socket drops", () => {
    const running = bot({
      id: "run",
      executionState: "running",
      connectionState: "live",
      attentionReason: "none",
    });
    const lost = markConnectionLost([running])[0];
    expect(lost.executionState).toBe("running");
    expect(lost.connectionState).toBe("last_known");
  });

  it("keeps the newer list row when a late GET is older", () => {
    const current = [
      bot({
        id: "mail",
        attentionReason: "none",
        executionState: "running",
        stateVersion: 8,
      }),
    ];
    const late = [
      bot({
        id: "mail",
        attentionReason: "approval",
        executionState: "waiting",
        stateVersion: 3,
        pendingConsentId: "cns_old",
      }),
    ];
    const merged = mergeBotList(current, late);
    expect(merged[0].attentionReason).toBe("none");
    expect(merged[0].executionState).toBe("running");
  });
});
