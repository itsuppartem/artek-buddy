import { createElement, createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Bot } from "../../types";
import { InboxList } from "./InboxList";

function bot(partial: Partial<Bot> & Pick<Bot, "id" | "name">): Bot {
  return {
    color: "#c4a574",
    preview: "hello",
    title: "hello",
    unread: false,
    pinned: false,
    status: "idle",
    ...partial,
  } as Bot;
}

describe("InboxList", () => {
  it("renders an unread inbox row and the archived count", () => {
    const html = renderToStaticMarkup(
      createElement(InboxList, {
        sidebarView: "inbox",
        query: "",
        bots: [bot({ id: "b1", name: "Lead", unread: true })],
        archived: [],
        archivedCount: 2,
        activeId: "b1",
        inboxPointerDown: createRef<string | null>(),
        onBackInbox: vi.fn(),
        onRestore: vi.fn(),
        onOpenBot: vi.fn(),
        onContextMenu: vi.fn(),
        onOpenArchived: vi.fn(),
      }),
    );
    expect(html).toContain('data-testid="bot-row"');
    expect(html).toContain('data-testid="unread-dot"');
    expect(html).toContain("open-archived");
    expect(html).toContain("archived-count");
    expect(html).toContain(">2<");
  });

  it("shows Restore on the archived list, not an inbox row", () => {
    const html = renderToStaticMarkup(
      createElement(InboxList, {
        sidebarView: "archived",
        query: "zzz-no-match",
        bots: [],
        archived: [],
        archivedCount: 0,
        activeId: undefined,
        inboxPointerDown: createRef<string | null>(),
        onBackInbox: vi.fn(),
        onRestore: vi.fn(),
        onOpenBot: vi.fn(),
        onContextMenu: vi.fn(),
        onOpenArchived: vi.fn(),
      }),
    );
    expect(html).toContain("back-inbox");
    expect(html).toContain("inbox-search-empty");
    expect(html).not.toContain('data-testid="bot-row"');
  });
});
