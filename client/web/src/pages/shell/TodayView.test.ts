import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Bot } from "../../types";
import { TodayView } from "./TodayView";

function bot(partial: Partial<Bot> & Pick<Bot, "id" | "name">): Bot {
  return {
    color: "#2864dc",
    title: "General help",
    description: "",
    instructions: "",
    preview: "",
    unread: false,
    pinned: false,
    status: "idle",
    ...partial,
  } as Bot;
}

describe("TodayView", () => {
  it("starts with an outcome and orders decisions before active work and results", () => {
    const html = renderToStaticMarkup(
      createElement(TodayView, {
        botsReady: true,
        bots: [
          bot({
            id: "working",
            name: "Research desk",
            status: "working",
            preview: "Reading source 3 of 4",
          }),
          bot({
            id: "ready",
            name: "Release helper",
            unread: true,
            preview: "Package report is ready",
          }),
          bot({
            id: "decision",
            name: "Mail",
            status: "waiting",
            unread: true,
            preview: "Needs approval to send",
          }),
        ],
        onOpenBot: vi.fn(),
        onStartTask: vi.fn(),
        onOpenRoutines: vi.fn(),
        onCreateBot: vi.fn(),
      }),
    );

    expect(html).toContain('data-testid="today-view"');
    expect(html).toContain("What needs doing?");
    expect(html).toContain('aria-label="Describe the outcome"');
    expect(html.indexOf("Needs your decision")).toBeLessThan(html.indexOf("In progress"));
    expect(html.indexOf("In progress")).toBeLessThan(html.indexOf("Ready for you"));
    expect(html).toContain("Mail");
    expect(html).toContain("Research desk");
    expect(html).toContain("Release helper");
    expect(html).toContain("Open routines");
  });

  it("does not mistake loading for an empty workspace", () => {
    const loading = renderToStaticMarkup(
      createElement(TodayView, {
        bots: [],
        botsReady: false,
        onOpenBot: vi.fn(),
        onStartTask: vi.fn(),
        onOpenRoutines: vi.fn(),
        onCreateBot: vi.fn(),
      }),
    );
    const empty = renderToStaticMarkup(
      createElement(TodayView, {
        bots: [],
        botsReady: true,
        onOpenBot: vi.fn(),
        onStartTask: vi.fn(),
        onOpenRoutines: vi.fn(),
        onCreateBot: vi.fn(),
      }),
    );

    expect(loading).toContain("Loading bots…");
    expect(empty).toContain("Create your first bot");
  });
});
