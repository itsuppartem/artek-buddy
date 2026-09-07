import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { RoutinesPanel } from "./RoutinesPanel";

describe("RoutinesPanel", () => {
  it("renders the New routine control", () => {
    const html = renderToStaticMarkup(
      createElement(RoutinesPanel, { botId: "bot_1", onLater: vi.fn() }),
    );
    expect(html).toContain("new-routine");
    expect(html).toContain("Routines");
  });
});
