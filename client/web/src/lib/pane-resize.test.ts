import { describe, expect, it } from "vitest";
import {
  clampPaneWidth,
  constrainPaneWidth,
  paneWidthAfterDrag,
  paneWidthAfterKey,
} from "./pane-resize";

describe("resizable shell panes", () => {
  it("resizes the left and right panes in the direction of the divider", () => {
    expect(paneWidthAfterDrag("left", 276, 80)).toBe(356);
    expect(paneWidthAfterDrag("right", 360, -80)).toBe(440);
  });

  it("keeps enough room for both the pane and conversation", () => {
    expect(clampPaneWidth("left", 100)).toBe(220);
    expect(clampPaneWidth("left", 900)).toBe(420);
    expect(clampPaneWidth("right", 100)).toBe(300);
    expect(clampPaneWidth("right", 900)).toBe(720);
  });

  it("supports keyboard resizing on the separator", () => {
    expect(paneWidthAfterKey("left", 276, "ArrowRight")).toBe(292);
    expect(paneWidthAfterKey("right", 360, "ArrowLeft")).toBe(376);
    expect(paneWidthAfterKey("right", 360, "Escape")).toBe(360);
  });

  it("preserves a usable conversation width", () => {
    expect(
      constrainPaneWidth("right", 700, {
        viewportWidth: 1200,
        otherPaneWidth: 276,
        railWidth: 88,
        separatorWidth: 8,
        conversationMinWidth: 360,
      }),
    ).toBe(460);
  });
});
