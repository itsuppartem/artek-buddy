import { createElement, createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Bot, ComputerStatus } from "../../types";
import { ComputerPane } from "./ComputerPane";

describe("ComputerPane", () => {
  it("keeps computer controls focused and does not duplicate bot settings", () => {
    const html = renderToStaticMarkup(
      createElement(ComputerPane, {
        bot: {
          id: "bot_test",
          name: "Research desk",
          title: "",
          description: "",
          instructions: "",
          color: "#2864dc",
          computerMode: "dedicated",
          notifyOnFinish: true,
          pinned: false,
          unread: false,
          preview: "",
          status: "idle",
        } as Bot,
        computer: null,
        screenUrl: null,
        screenError: null,
        screenEpoch: 0,
        previewFrameRef: createRef<HTMLIFrameElement>(),
        booting: false,
        onClose: vi.fn(),
        onOpenFullscreen: vi.fn(),
        onStart: vi.fn(),
        onTakeControl: vi.fn(),
        onRelease: vi.fn(),
        onRetryScreen: vi.fn(),
        onScreenFrameLoad: vi.fn(),
        onLater: vi.fn(),
      }),
    );

    expect(html).toContain(">Close<");
    expect(html).not.toContain(">Settings<");
    expect(html).not.toContain(">Memory<");
    expect(html).not.toContain(">Routines<");
  });

  it("does not show a stale preview after the desktop goes to sleep", () => {
    const bot = {
      id: "bot_sleeping",
      name: "Sleeping desk",
      title: "",
      description: "",
      instructions: "",
      color: "#2864dc",
      computerMode: "dedicated",
      notifyOnFinish: true,
      pinned: false,
      unread: false,
      preview: "",
      status: "idle",
    } as Bot;
    const computer = {
      botId: bot.id,
      busyBotName: null,
      controlHolder: "none",
      homeRevision: null,
      kind: "private",
      mode: "dedicated",
      screenAvailable: false,
      state: "suspended",
    } as ComputerStatus;

    const html = renderToStaticMarkup(
      createElement(ComputerPane, {
        bot,
        computer,
        screenUrl: "/novnc/stale/embed.html?view_only=true",
        screenError: "Desktop is starting…",
        screenEpoch: 1,
        previewFrameRef: createRef<HTMLIFrameElement>(),
        booting: false,
        onClose: vi.fn(),
        onOpenFullscreen: vi.fn(),
        onStart: vi.fn(),
        onTakeControl: vi.fn(),
        onRelease: vi.fn(),
        onRetryScreen: vi.fn(),
        onScreenFrameLoad: vi.fn(),
      }),
    );

    expect(html).toContain("Sleeping • Click to start");
    expect(html).not.toContain("<iframe");
    expect(html).not.toContain("Desktop is starting…");
  });
});
