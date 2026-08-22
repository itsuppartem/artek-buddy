import { describe, expect, it } from "vitest";
import { embeddableScreenUrl, shouldAutoBoot, shouldTakeControl } from "./screen";

describe("embeddableScreenUrl", () => {
  it("only embeds the host /novnc/ path", () => {
    expect(embeddableScreenUrl("/novnc/box/1/view")).toBe("/novnc/box/1/view");
    expect(embeddableScreenUrl("https://evil.example/novnc/x")).toBeNull();
    expect(embeddableScreenUrl(null)).toBeNull();
  });
});

describe("shouldTakeControl", () => {
  it("boots from the button, not from a preview click", () => {
    expect(shouldTakeControl("button")).toBe(true);
    expect(shouldTakeControl("preview")).toBe(false);
  });
});

describe("shouldAutoBoot", () => {
  it("does not boot again while already booting or in error", () => {
    expect(shouldAutoBoot("booting", null, false)).toBe(false);
    expect(shouldAutoBoot("error", null, false)).toBe(false);
  });
});
