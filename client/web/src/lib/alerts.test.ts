import { describe, expect, it } from "vitest";
import type { ProductEvent } from "../types";
import {
  allowAlert,
  attentionFingerprint,
  attentionFromBotChange,
  attentionFromEvent,
  attentionFromParkedBot,
  type BotAlertSnapshot,
  isHistoricalEvent,
  parkedAttentionForView,
  rememberShownAlert,
  shouldClearAttentionForView,
  shouldReplaceAttention,
  shouldSendDesktopAlert,
  shouldWatchBackgroundBot,
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

function botSnap(over: Partial<BotAlertSnapshot>): BotAlertSnapshot {
  return {
    id: "bot-a",
    name: "Need",
    status: "idle",
    unread: false,
    preview: "",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

describe("shouldClearAttentionForView", () => {
  it("clears the banner only for the chat already on screen", () => {
    const takeover = attentionFromEvent(event({ type: "computer.takeover.requested" }), "Need");
    expect(takeover).not.toBeNull();
    expect(shouldClearAttentionForView(takeover, "bot-a")).toBe(true);
    expect(shouldClearAttentionForView(takeover, "bot-b")).toBe(false);
    expect(shouldClearAttentionForView(null, "bot-a")).toBe(false);
  });
});

describe("shouldReplaceAttention", () => {
  it("does not let a later replied alert replace takeover", () => {
    const takeover = attentionFromEvent(
      event({ type: "computer.takeover.requested", createdAt: "2026-01-01T00:00:00Z" }),
      "Need",
    );
    const replied = attentionFromEvent(
      event({ type: "run.completed", createdAt: "2026-01-01T00:00:01Z" }),
      "Need",
    );
    expect(takeover?.title).toBe("Need needs you");
    expect(replied?.title).toBe("Need replied");
    expect(takeover && replied && shouldReplaceAttention(takeover, replied)).toBe(false);
  });

  it("replaces replied with a later takeover", () => {
    const replied = attentionFromEvent(event({ type: "run.completed" }), "Need");
    const takeover = attentionFromEvent(
      event({ type: "computer.takeover.requested", createdAt: "2026-01-01T00:00:02Z" }),
      "Need",
    );
    expect(replied && takeover && shouldReplaceAttention(replied, takeover)).toBe(true);
  });
});

describe("attentionFromBotChange", () => {
  it("raises takeover when the bot enters waiting_takeover", () => {
    const alert = attentionFromBotChange(
      botSnap({ status: "running" }),
      botSnap({
        status: "waiting_takeover",
        unread: true,
        preview: "need you",
        updatedAt: "2026-01-01T00:00:02Z",
      }),
    );
    expect(alert?.kind).toBe("takeover");
    expect(alert?.title).toBe("Need needs you");
  });

  it("does not emit replied while the bot stays waiting_takeover", () => {
    expect(
      attentionFromBotChange(
        botSnap({ status: "waiting_takeover", unread: false }),
        botSnap({
          status: "waiting_takeover",
          unread: true,
          preview: "need you",
          updatedAt: "2026-01-01T00:00:02Z",
        }),
      ),
    ).toBeNull();
  });

  it("treats running to idle unread as replied even if the preview is a takeover reason", () => {
    const alert = attentionFromBotChange(
      botSnap({ status: "running" }),
      botSnap({
        status: "idle",
        unread: true,
        preview: "Pass the site check, then Release.",
        updatedAt: "2026-01-01T00:00:02Z",
      }),
    );
    expect(alert?.kind).toBe("replied");
    expect(alert?.title).toBe("Need replied");
  });
});

describe("attentionFromParkedBot", () => {
  it("raises takeover from a bot that is already waiting_takeover", () => {
    const alert = attentionFromParkedBot(
      botSnap({
        status: "waiting_takeover",
        preview: "Pass the site check, then Release.",
        updatedAt: "2026-01-01T00:00:02Z",
      }),
    );
    expect(alert?.kind).toBe("takeover");
    expect(alert?.title).toBe("Need needs you");
  });

  it("does not raise from idle or waiting_input", () => {
    expect(attentionFromParkedBot(botSnap({ status: "idle" }))).toBeNull();
    expect(attentionFromParkedBot(botSnap({ status: "waiting_input" }))).toBeNull();
  });
});

describe("parkedAttentionForView", () => {
  const speaker = botSnap({
    id: "bot-a",
    name: "Need",
    status: "waiting_takeover",
    updatedAt: "2026-01-01T00:00:02Z",
  });
  const watcher = botSnap({
    id: "bot-b",
    name: "Idle",
    status: "idle",
    updatedAt: "2026-01-01T00:00:03Z",
  });

  it("shows needs you on the other chat, not on the parked chat", () => {
    expect(parkedAttentionForView([speaker, watcher], "bot-b", new Set())?.title).toBe(
      "Need needs you",
    );
    expect(parkedAttentionForView([speaker, watcher], "bot-a", new Set())).toBeNull();
  });

  it("does not resurrect a dismissed takeover", () => {
    const alert = attentionFromParkedBot(speaker);
    expect(alert).not.toBeNull();
    if (!alert) return;
    const dismissed = new Set([attentionFingerprint(alert)]);
    expect(parkedAttentionForView([speaker, watcher], "bot-b", dismissed)).toBeNull();
  });

  it("ignores a takeover parked before the window opened", () => {
    const leftover = botSnap({
      status: "waiting_takeover",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    const opened = Date.parse("2026-01-01T00:00:01Z");
    expect(parkedAttentionForView([leftover, watcher], "bot-b", new Set(), opened)).toBeNull();
    expect(parkedAttentionForView([speaker, watcher], "bot-b", new Set(), opened)?.title).toBe(
      "Need needs you",
    );
  });
});

describe("shouldWatchBackgroundBot", () => {
  it("watches a parked other chat the same way as a running one", () => {
    expect(shouldWatchBackgroundBot("waiting_takeover", "bot-a", "bot-b")).toBe(true);
    expect(shouldWatchBackgroundBot("running", "bot-a", "bot-b")).toBe(true);
    expect(shouldWatchBackgroundBot("queued", "bot-a", "bot-b")).toBe(true);
    expect(shouldWatchBackgroundBot("leased", "bot-a", "bot-b")).toBe(true);
  });

  it("does not watch the open chat or an idle row", () => {
    expect(shouldWatchBackgroundBot("waiting_takeover", "bot-a", "bot-a")).toBe(false);
    expect(shouldWatchBackgroundBot("idle", "bot-a", "bot-b")).toBe(false);
    expect(shouldWatchBackgroundBot("waiting_input", "bot-a", "bot-b")).toBe(false);
  });
});

describe("rememberShownAlert", () => {
  it("does not consume the parked key when the same kind is still in the debounce window", () => {
    const seen = new Set<string>();
    const recentKindAt = new Map<string, number>([["bot-a:takeover", 1_000]]);
    expect(
      rememberShownAlert(seen, recentKindAt, "bot-a:takeover:parked", "bot-a:takeover", 4_000),
    ).toBe("skip");
    expect(seen.has("bot-a:takeover:parked")).toBe(false);
  });

  it("can show the same parked key after the debounce window", () => {
    const seen = new Set<string>();
    const recentKindAt = new Map<string, number>([["bot-a:takeover", 1_000]]);
    expect(
      rememberShownAlert(seen, recentKindAt, "bot-a:takeover:parked", "bot-a:takeover", 10_000),
    ).toBe("show");
    expect(seen.has("bot-a:takeover:parked")).toBe(true);
    expect(recentKindAt.get("bot-a:takeover")).toBe(10_000);
  });

  it("skips a key that already showed", () => {
    const seen = new Set<string>(["bot-a:takeover:parked"]);
    const recentKindAt = new Map<string, number>();
    expect(
      rememberShownAlert(seen, recentKindAt, "bot-a:takeover:parked", "bot-a:takeover", 20_000),
    ).toBe("skip");
    expect(recentKindAt.size).toBe(0);
  });
});
