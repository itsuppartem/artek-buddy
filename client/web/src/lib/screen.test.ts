import { describe, expect, it } from "vitest";
import {
  embeddableScreenUrl,
  shouldAutoBoot,
  shouldReportOwnerActivity,
  shouldTakeControl,
} from "./screen";

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

describe("shouldReportOwnerActivity", () => {
  it("throttles overlay motion so a heartbeat-like poll is not implied", () => {
    expect(shouldReportOwnerActivity(1_000, 1_000)).toBe(false);
    expect(shouldReportOwnerActivity(1_000, 5_999)).toBe(false);
    expect(shouldReportOwnerActivity(1_000, 6_000)).toBe(true);
  });
});
