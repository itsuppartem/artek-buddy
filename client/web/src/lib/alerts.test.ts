import { describe, expect, it } from "vitest";
import type { ProductEvent } from "../types";
import {
  alertKeysToRemember,
  allowAlert,
  attentionFingerprint,
  attentionFromEvent,
  attentionFromParkedBot,
  type BotAlertSnapshot,
  desktopWindowFocused,
  isHistoricalEvent,
  nativeNotifyTag,
  parkedAttentionForView,
  parkedTakeoverKey,
  rememberShownAlert,
  shouldClearAttentionForView,
  shouldConsiderEventForAttention,
  shouldCountThreadRead,
  shouldReplaceAttention,
  shouldSendDesktopAlert,
  shouldSendNativeAlert,
  shouldStickDismissOnView,
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

function completedEvent(text = "Done", runId = "run-1", eventId = "e1"): ProductEvent {
  return event({
    id: eventId,
    type: "run.completed",
    runId,
    payload: {
      message: {
        id: "msg-1",
        role: "bot",
        blocks: [{ kind: "text", text }],
      },
    },
  });
}

describe("shouldSendDesktopAlert", () => {
  it("skips a banner for the chat already on a focused window", () => {
    expect(
      shouldSendDesktopAlert({ windowFocused: true, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(false);
  });

  it("alerts when another chat is open", () => {
    expect(
      shouldSendDesktopAlert({ windowFocused: true, viewingBotId: "bot-b", alertBotId: "bot-a" }),
    ).toBe(true);
  });

  it("alerts the open chat when the window is unfocused even if the page is still visible", () => {
    expect(
      shouldSendDesktopAlert({
        windowFocused: false,
        pageHidden: false,
        viewingBotId: "bot-a",
        alertBotId: "bot-a",
      }),
    ).toBe(true);
  });

  it("alerts the open chat when the window is hidden", () => {
    expect(
      shouldSendDesktopAlert({
        windowFocused: false,
        pageHidden: true,
        viewingBotId: "bot-a",
        alertBotId: "bot-a",
      }),
    ).toBe(true);
  });
});

describe("desktopWindowFocused", () => {
  it("uses the browser focus only when GTK has not spoken", () => {
    expect(desktopWindowFocused({ gtkActive: null, pageHidden: false, browserFocused: true })).toBe(
      true,
    );
    expect(
      desktopWindowFocused({ gtkActive: null, pageHidden: false, browserFocused: false }),
    ).toBe(false);
  });

  it("treats an inactive GTK window as unfocused even when WebKit still reports hasFocus", () => {
    expect(
      desktopWindowFocused({ gtkActive: false, pageHidden: false, browserFocused: true }),
    ).toBe(false);
  });

  it("is unfocused while the page is hidden", () => {
    expect(desktopWindowFocused({ gtkActive: true, pageHidden: true, browserFocused: true })).toBe(
      false,
    );
  });
});

describe("shouldSendNativeAlert", () => {
  it("posts for the open chat when GTK says the window is inactive even if WebKit still hasFocus", () => {
    expect(
      shouldSendNativeAlert({
        gtkWindowActive: false,
        windowFocused: true,
        pageHidden: false,
        viewingBotId: "bot-a",
        alertBotId: "bot-a",
      }),
    ).toBe(true);
  });

  it("stays quiet for the open chat while the GTK window is focused", () => {
    expect(
      shouldSendNativeAlert({
        gtkWindowActive: true,
        windowFocused: true,
        pageHidden: false,
        viewingBotId: "bot-a",
        alertBotId: "bot-a",
      }),
    ).toBe(false);
  });

  it("uses browser focus when there is no GTK window", () => {
    expect(
      shouldSendNativeAlert({
        gtkWindowActive: null,
        windowFocused: true,
        pageHidden: false,
        viewingBotId: "bot-a",
        alertBotId: "bot-a",
      }),
    ).toBe(false);
    expect(
      shouldSendNativeAlert({
        gtkWindowActive: null,
        windowFocused: false,
        pageHidden: false,
        viewingBotId: "bot-a",
        alertBotId: "bot-a",
      }),
    ).toBe(true);
  });
});

describe("shouldCountThreadRead", () => {
  it("counts a chat as read only while that thread is focused on screen", () => {
    expect(
      shouldCountThreadRead({
        viewingBotId: "bot-a",
        chatId: "bot-a",
        windowFocused: true,
        pageHidden: false,
      }),
    ).toBe(true);
    expect(
      shouldCountThreadRead({
        viewingBotId: "bot-a",
        chatId: "bot-a",
        windowFocused: false,
        pageHidden: false,
      }),
    ).toBe(false);
    expect(
      shouldCountThreadRead({
        viewingBotId: "bot-b",
        chatId: "bot-a",
        windowFocused: true,
        pageHidden: false,
      }),
    ).toBe(false);
    expect(
      shouldCountThreadRead({
        viewingBotId: "bot-a",
        chatId: "bot-a",
        windowFocused: true,
        pageHidden: false,
        gtkWindowActive: false,
      }),
    ).toBe(false);
  });
});

describe("nativeNotifyTag", () => {
  it("is stable per bot so the OS can replace a stacked alert", () => {
    expect(nativeNotifyTag("bot-a")).toBe("artek-buddy:bot-a");
    expect(nativeNotifyTag("bot-a")).toBe(nativeNotifyTag("bot-a"));
    expect(nativeNotifyTag("bot-b")).not.toBe(nativeNotifyTag("bot-a"));
  });
});

describe("attentionFromEvent", () => {
  it("uses only the workspace stream as the canonical attention source", () => {
    expect(shouldConsiderEventForAttention("workspace")).toBe(true);
    expect(shouldConsiderEventForAttention("thread")).toBe(false);
    expect(shouldConsiderEventForAttention("poll")).toBe(false);
  });

  it("deduplicates one occurrence without suppressing a later identical reply", () => {
    const first = attentionFromEvent(completedEvent("Same answer", "run-1", "evt-a"), "Alpha");
    const duplicate = attentionFromEvent(completedEvent("Same answer", "run-1", "evt-a"), "Alpha");
    const later = attentionFromEvent(completedEvent("Same answer", "run-2", "evt-b"), "Alpha");
    expect(first).not.toBeNull();
    expect(duplicate).not.toBeNull();
    expect(later).not.toBeNull();
    if (!first || !duplicate || !later) return;
    expect(attentionFingerprint(first)).toBe(attentionFingerprint(duplicate));
    expect(attentionFingerprint(first)).not.toBe(attentionFingerprint(later));
  });

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

  it("treats a parked owner question as an ask", () => {
    expect(
      attentionFromEvent(
        event({
          type: "run.waiting_input",
          payload: { text: "Please complete the browser step.", messageId: "msg-ask" },
        }),
        "Alpha",
      ),
    ).toMatchObject({
      kind: "ask",
      title: "Alpha is asking",
      body: "Please complete the browser step.",
    });
  });

  it("notifies only when completion created a new owner-visible final message", () => {
    expect(attentionFromEvent(completedEvent("Fresh final answer"), "Alpha")).toMatchObject({
      kind: "replied",
      body: "Fresh final answer",
    });
    expect(
      attentionFromEvent(
        event({
          type: "run.completed",
          runId: "run-silent",
          payload: { message: null },
        }),
        "Alpha",
      ),
    ).toBeNull();
  });

  it("does not turn an intermediate text event into a native alert", () => {
    expect(
      attentionFromEvent(
        event({
          type: "thread.message.created",
          payload: {
            message: {
              id: "msg-progress",
              role: "bot",
              blocks: [{ kind: "text", text: "Still working" }],
            },
          },
        }),
        "Alpha",
      ),
    ).toBeNull();
  });

  it("does not duplicate ask attention from the ask-card message event", () => {
    expect(
      attentionFromEvent(
        event({
          type: "thread.message.created",
          payload: {
            message: {
              id: "msg-ask",
              role: "bot",
              blocks: [{ kind: "ask", text: "Pick one", status: "pending" }],
            },
          },
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
    const replied = attentionFromEvent(completedEvent(), "Alpha");
    const ask = attentionFromEvent(
      event({ type: "run.waiting_input", payload: { text: "Pick one" } }),
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
      { ...completedEvent(), createdAt: "2026-01-01T00:00:01Z" },
      "Need",
    );
    expect(takeover?.title).toBe("Need needs you");
    expect(replied?.title).toBe("Need replied");
    expect(takeover && replied && shouldReplaceAttention(takeover, replied)).toBe(false);
  });

  it("replaces replied with a later takeover", () => {
    const replied = attentionFromEvent(completedEvent(), "Need");
    const takeover = attentionFromEvent(
      event({ type: "computer.takeover.requested", createdAt: "2026-01-01T00:00:02Z" }),
      "Need",
    );
    expect(replied && takeover && shouldReplaceAttention(replied, takeover)).toBe(true);
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

  it("still raises a bot created in this window even if its stamp looks older than open", () => {
    const opened = Date.parse("2026-01-01T00:00:10Z");
    const createdHere = botSnap({
      id: "bot-new",
      name: "AskA",
      status: "waiting_takeover",
      updatedAt: "2026-01-01T00:00:01Z",
    });
    expect(
      parkedAttentionForView(
        [createdHere, watcher],
        "bot-b",
        new Set(),
        opened,
        new Set(["bot-new"]),
      )?.title,
    ).toBe("AskA needs you");
    expect(parkedAttentionForView([createdHere, watcher], "bot-b", new Set(), opened)).toBeNull();
  });
});

describe("shouldStickDismissOnView", () => {
  const takeover = attentionFromEvent(event({ type: "computer.takeover.requested" }), "Need");

  it("does not stick dismiss when the parked chat was already open", () => {
    expect(shouldStickDismissOnView(takeover, "bot-a", "bot-a")).toBe(false);
    expect(shouldStickDismissOnView(takeover, "bot-a", null)).toBe(false);
  });

  it("sticks dismiss only when switching onto the parked chat", () => {
    expect(shouldStickDismissOnView(takeover, "bot-a", "bot-b")).toBe(true);
    expect(shouldStickDismissOnView(takeover, "bot-b", "bot-a")).toBe(false);
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
  it("does not suppress distinct final answers that finish close together", () => {
    const seen = new Set<string>();
    expect(rememberShownAlert(seen, "event-a")).toBe("show");
    expect(rememberShownAlert(seen, "event-b")).toBe("show");
    expect(seen).toEqual(new Set(["event-a", "event-b"]));
  });

  it("skips a key that already showed", () => {
    const seen = new Set<string>(["bot-a:takeover:parked"]);
    expect(rememberShownAlert(seen, "bot-a:takeover:parked")).toBe("skip");
  });
});

describe("alertKeysToRemember", () => {
  it("does not consume keys when the banner was suppressed because this chat is open", () => {
    expect(
      alertKeysToRemember({
        key: "evt-1",
        fingerprint: "bot-a:takeover:run-1",
        botId: "bot-a",
        kind: "takeover",
        surfaced: false,
      }),
    ).toEqual([]);
  });

  it("records the parked key only after a takeover actually surfaces", () => {
    expect(
      alertKeysToRemember({
        key: "evt-1",
        fingerprint: "bot-a:takeover:run-1",
        botId: "bot-a",
        kind: "takeover",
        surfaced: true,
      }),
    ).toEqual(["evt-1", "bot-a:takeover:run-1", parkedTakeoverKey("bot-a")]);
  });

  it("does not invent a parked key for a reply", () => {
    expect(
      alertKeysToRemember({
        key: "evt-2",
        fingerprint: "bot-a:replied:run-2",
        botId: "bot-a",
        kind: "replied",
        surfaced: true,
      }),
    ).toEqual(["evt-2", "bot-a:replied:run-2"]);
  });
});
