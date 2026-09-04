import { createElement, createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Bot } from "../../types";
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
});
