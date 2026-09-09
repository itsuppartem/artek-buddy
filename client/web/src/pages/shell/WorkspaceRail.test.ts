import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceRail } from "./WorkspaceRail";

describe("WorkspaceRail", () => {
  it("keeps each top-level destination visible once", () => {
    const html = renderToStaticMarkup(
      createElement(WorkspaceRail, {
        active: "today",
        attentionCount: 2,
        onToday: vi.fn(),
        onChats: vi.fn(),
        onRoutines: vi.fn(),
        onLibrary: vi.fn(),
      }),
    );

    expect(html).toContain('data-testid="workspace-rail"');
    expect(html).toContain(">Today<");
    expect(html).toContain(">Chats<");
    expect(html).toContain(">Routines<");
    expect(html).toContain(">Library<");
    expect(html).not.toContain(">Settings<");
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('data-testid="workspace-attention-count"');
  });
});
