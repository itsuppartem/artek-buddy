import { describe, expect, it } from "vitest";
import {
  embeddableScreenUrl,
  shouldAutoBoot,
  shouldFetchScreenUrl,
  shouldReplaceScreenUrl,
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
  it("only Take control grants control; start and preview stay view-only", () => {
    expect(shouldTakeControl("button")).toBe(true);
    expect(shouldTakeControl("preview")).toBe(false);
    expect(shouldTakeControl("start")).toBe(false);
  });
});

describe("shouldFetchScreenUrl", () => {
  it("loads the screen when the pane is open on a running box", () => {
    expect(shouldFetchScreenUrl(true, false, "running")).toBe(true);
    expect(shouldFetchScreenUrl(false, true, "booting")).toBe(true);
    expect(shouldFetchScreenUrl(false, false, "running")).toBe(false);
    expect(shouldFetchScreenUrl(true, false, "stopped")).toBe(false);
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

describe("shouldReplaceScreenUrl", () => {
  const view =
    "/novnc/YWJj/6080/view/9999999999999.abcdefghijklmnopqrstuvwxyz0123456789ABC/embed.html?view_only=true";
  const control =
    "/novnc/YWJj/6081/control/9999999999999.abcdefghijklmnopqrstuvwxyz0123456789ABC/embed.html?view_only=false";

  it("switches the iframe off a dead control URL after Release", () => {
    expect(shouldReplaceScreenUrl(control, view)).toBe(true);
    expect(shouldReplaceScreenUrl(view, control)).toBe(true);
  });

  it("does not reload the same view-only target on every poll", () => {
    expect(shouldReplaceScreenUrl(view, view)).toBe(false);
  });

  it("drops a control URL when the next screen is missing", () => {
    expect(shouldReplaceScreenUrl(control, null)).toBe(true);
  });
});
