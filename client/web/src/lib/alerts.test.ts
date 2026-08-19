import { describe, expect, it } from "vitest";
import {
  allowAlert,
  attentionFromBotChange,
  attentionFromEvent,
  isHistoricalEvent,
  shouldSendDesktopAlert,
  type AttentionAlert,
  type BotAlertSnapshot,
} from "./alerts";
import type { ProductEvent } from "../types";

function event(partial: Partial<ProductEvent> & Pick<ProductEvent, "type">): ProductEvent {
  return {
    id: "evt_1",
    workspaceId: "ws_1",
    threadId: "th_1",
    botId: "bot_1",
    seq: 1,
    createdAt: "2026-08-18T12:00:00.000Z",
    payload: {},
    ...partial,
  };
}

function bot(partial: Partial<BotAlertSnapshot> = {}): BotAlertSnapshot {
  return {
    id: "bot_1",
    name: "Weather",
    status: "running",
    unread: false,
    preview: "",
    updatedAt: "2026-08-18T12:00:00.000Z",
    ...partial,
  };
}

function alert(partial: Partial<AttentionAlert> = {}): AttentionAlert {
  return {
    kind: "replied",
    botId: "bot_1",
    title: "Weather replied",
    body: "",
    urgency: "normal",
    ...partial,
  };
}

describe("attentionFromEvent", () => {
  it("classifies a finished run as a reply", () => {
    const result = attentionFromEvent(event({ type: "run.completed" }), "Weather");
    expect(result).toMatchObject({
      kind: "replied",
      botId: "bot_1",
      title: "Weather replied",
      urgency: "normal",
    });
  });

  it("classifies a failed run as critical", () => {
    const result = attentionFromEvent(
      event({ type: "run.failed", payload: { error: "model timeout" } }),
      "Weather",
    );
    expect(result).toMatchObject({
      kind: "failed",
      title: "Weather failed",
      body: "model timeout",
      urgency: "critical",
    });
  });

  it("treats takeover and waiting-input as needing the user", () => {
    expect(
      attentionFromEvent(event({ type: "computer.takeover.requested" }), "Weather")?.kind,
    ).toBe("takeover");
    expect(attentionFromEvent(event({ type: "run.waiting_input" }), "Weather")?.kind).toBe(
      "takeover",
    );
    expect(
      attentionFromEvent(
        event({ type: "run.waiting_input", payload: { consentId: "cns_1" } }),
        "Weather",
      ),
    ).toBeNull();
    expect(
      attentionFromEvent(
        event({ type: "run.waiting_input", payload: { auto: true, path: "/tmp/a" } }),
        "Weather",
      ),
    ).toBeNull();
  });

  it("alerts on a pending ask card, not on ordinary send_message text", () => {
    const ask = attentionFromEvent(
      event({
        type: "thread.message.created",
        payload: {
          message: {
            blocks: [{ kind: "ask", text: "Ship it?", status: "pending" }],
          },
        },
      }),
      "Weather",
    );
    expect(ask).toMatchObject({ kind: "ask", body: "Ship it?", urgency: "critical" });

    const text = attentionFromEvent(
      event({
        type: "thread.message.created",
        payload: { message: { blocks: [{ kind: "text", text: "Working on it" }] } },
      }),
      "Weather",
    );
    expect(text).toBeNull();
  });

  it("ignores answered ask cards and token noise", () => {
    expect(
      attentionFromEvent(
        event({
          type: "thread.message.created",
          payload: {
            message: { blocks: [{ kind: "ask", text: "Done?", status: "answered" }] },
          },
        }),
        "Weather",
      ),
    ).toBeNull();
    expect(attentionFromEvent(event({ type: "thread.progress" }), "Weather")).toBeNull();
    expect(attentionFromEvent(event({ type: "run.started" }), "Weather")).toBeNull();
  });

  it("accepts the reserved thread.ask event", () => {
    expect(
      attentionFromEvent(
        event({ type: "thread.ask", payload: { question: "Which city?" } }),
        "Weather",
      ),
    ).toMatchObject({ kind: "ask", body: "Which city?" });
  });
});

describe("attentionFromBotChange", () => {
  it("alerts when a background bot leaves running with unread", () => {
    const result = attentionFromBotChange(
      bot({ status: "running", unread: true, preview: "looking up" }),
      bot({
        status: "idle",
        unread: true,
        preview: "**Belgrade** is 24C",
        updatedAt: "2026-08-18T12:01:00.000Z",
      }),
    );
    expect(result).toMatchObject({
      kind: "replied",
      body: "Belgrade is 24C",
    });
  });

  it("does not treat intermediate unread-while-running as an ask", () => {
    expect(
      attentionFromBotChange(
        bot({ status: "running", unread: false }),
        bot({ status: "running", unread: true, preview: "Working on it" }),
      ),
    ).toBeNull();
  });

  it("alerts on takeover and failed status flips", () => {
    expect(
      attentionFromBotChange(bot({ status: "running" }), bot({ status: "waiting_takeover" }))
        ?.kind,
    ).toBe("takeover");
    expect(
      attentionFromBotChange(
        bot({ status: "running", unread: true }),
        bot({ status: "error", unread: true, preview: "boom" }),
      ),
    ).toMatchObject({ kind: "failed", body: "boom" });
  });

  it("skips a finish that is already read", () => {
    expect(
      attentionFromBotChange(
        bot({ status: "running", unread: false }),
        bot({ status: "idle", unread: false }),
      ),
    ).toBeNull();
  });
});

describe("allowAlert and desktop skip", () => {
  it("honors notifyOnFinish only for reply and failure", () => {
    expect(allowAlert(alert({ kind: "replied" }), false)).toBe(false);
    expect(allowAlert(alert({ kind: "failed" }), false)).toBe(false);
    expect(allowAlert(alert({ kind: "ask" }), false)).toBe(true);
    expect(allowAlert(alert({ kind: "takeover" }), false)).toBe(true);
    expect(allowAlert(alert({ kind: "replied" }), true)).toBe(true);
  });

  it("skips the OS notify when the window is focused on that bot", () => {
    expect(
      shouldSendDesktopAlert({
        windowFocused: true,
        viewingBotId: "bot_1",
        alertBotId: "bot_1",
      }),
    ).toBe(false);
    expect(
      shouldSendDesktopAlert({
        windowFocused: true,
        viewingBotId: "bot_1",
        alertBotId: "bot_2",
      }),
    ).toBe(true);
    expect(
      shouldSendDesktopAlert({
        windowFocused: false,
        viewingBotId: "bot_1",
        alertBotId: "bot_1",
      }),
    ).toBe(true);
  });
});

describe("isHistoricalEvent", () => {
  it("drops buffered events from before subscribe, with clock skew slack", () => {
    const subscribedAt = Date.parse("2026-08-18T12:00:00.000Z");
    expect(
      isHistoricalEvent({ createdAt: "2026-08-18T11:59:50.000Z" }, subscribedAt),
    ).toBe(true);
    expect(
      isHistoricalEvent({ createdAt: "2026-08-18T11:59:59.000Z" }, subscribedAt),
    ).toBe(false);
    expect(isHistoricalEvent({ createdAt: "not-a-date" }, subscribedAt)).toBe(false);
  });
});
