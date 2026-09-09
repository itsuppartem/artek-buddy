import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { PaneResizeHandle } from "./PaneResizeHandle";

describe("PaneResizeHandle", () => {
  it("uses the full shell height as its pointer target", () => {
    const html = renderToStaticMarkup(
      createElement(PaneResizeHandle, {
        pane: "left",
        width: 276,
        defaultWidth: 276,
        onChange: vi.fn(),
      }),
    );

    expect(html).toContain("h-full");
    expect(html).toContain("<hr");
  });
});
