import { describe, expect, it } from "vitest";
import type { ProductEvent } from "../types";
import {
  allowAlert,
  attentionFromEvent,
  isHistoricalEvent,
  shouldSendDesktopAlert,
} from "./alerts";

function event(over: Partial<ProductEvent> & Pick<ProductEvent, "type">): ProductEvent {
  return {
    id: "e1",
    workspaceId: "w",
    threadId: "t",
    botId: "bot-a",
    seq: 1,
    createdAt: "2026-01-01T00:00:00Z",
    payload: {},
    ...over,
  };
}

describe("shouldSendDesktopAlert", () => {
  it("skips a banner for the chat already on a focused window", () => {
    expect(
      shouldSendDesktopAlert({ windowFocused: true, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(false);
  });

  it("alerts when the window is focused on another chat or unfocused", () => {
    expect(
      shouldSendDesktopAlert({ windowFocused: true, viewingBotId: "bot-b", alertBotId: "bot-a" }),
    ).toBe(true);
    expect(
      shouldSendDesktopAlert({ windowFocused: false, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(true);
  });
});

describe("attentionFromEvent", () => {
  it("does not treat auto owner jobs as takeover", () => {
    expect(
      attentionFromEvent(
        event({
          type: "run.waiting_input",
          payload: { auto: true, consentId: "c1", actionClass: "owner_read" },
        }),
        "Alpha",
      ),
    ).toBeNull();
  });

  it("builds a failed alert from run.failed", () => {
    const alert = attentionFromEvent(
      event({ type: "run.failed", payload: { error: "boom" } }),
      "Alpha",
    );
    expect(alert).toMatchObject({ kind: "failed", title: "Alpha failed", body: "boom" });
  });
});

describe("allowAlert", () => {
  it("honors notifyOnFinish only for replied and failed", () => {
    const replied = attentionFromEvent(event({ type: "run.completed" }), "Alpha");
    const ask = attentionFromEvent(
      event({ type: "thread.ask", payload: { text: "Pick one" } }),
      "Alpha",
    );
    expect(replied && allowAlert(replied, false)).toBe(false);
    expect(replied && allowAlert(replied, true)).toBe(true);
    expect(ask && allowAlert(ask, false)).toBe(true);
  });
});

describe("isHistoricalEvent", () => {
  it("treats events before the window opened as history", () => {
    const opened = Date.parse("2026-01-01T00:00:00Z");
    expect(isHistoricalEvent(event({ type: "run.completed" }), opened + 1)).toBe(true);
    expect(isHistoricalEvent(event({ type: "run.completed" }), opened - 1)).toBe(false);
  });
});
