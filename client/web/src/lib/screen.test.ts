import { describe, expect, it } from "vitest";
import {
  computerLabel,
  embeddableScreenUrl,
  overlayPointerEvents,
  previewPointerEvents,
  shouldAutoBoot,
  shouldRefreshScreenUrl,
  shouldReplaceScreenUrl,
  shouldTakeControl,
  screenTargetKey,
} from "./screen";

const SIG = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";

function signed(policy: "view" | "control", expires: number, port = 16080): string {
  return `/novnc/abc/${port}/${policy}/${expires}.${SIG}/embed.html?view_only=${policy === "view"}`;
}

describe("embeddableScreenUrl", () => {
  it("keeps signed same-origin paths", () => {
    expect(embeddableScreenUrl("/novnc/abc/16080/view/1.sig/embed.html")).toBe(
      "/novnc/abc/16080/view/1.sig/embed.html",
    );
  });

  it("rejects unsigned raw screen ports", () => {
    expect(embeddableScreenUrl("http://127.0.0.1:6080/embed.html")).toBeNull();
    expect(embeddableScreenUrl("http://127.0.0.1:16080/embed.html")).toBeNull();
    expect(embeddableScreenUrl("//evil/novnc/x")).toBeNull();
  });
});

describe("computer pane helpers", () => {
  it("preview never accepts pointer events", () => {
    expect(previewPointerEvents()).toBe("none");
  });

  it("overlay accepts input only while the user holds control", () => {
    expect(overlayPointerEvents("user")).toBe("auto");
    expect(overlayPointerEvents("bot")).toBe("none");
    expect(overlayPointerEvents("none")).toBe("none");
  });

  it("takes control only from the button, not the thumbnail", () => {
    expect(shouldTakeControl("preview")).toBe(false);
    expect(shouldTakeControl("button")).toBe(true);
  });

  it("auto-boots a stopped pane once", () => {
    expect(shouldAutoBoot("stopped", null, false)).toBe(true);
    expect(shouldAutoBoot("running", "/novnc/x", true)).toBe(false);
    expect(shouldAutoBoot("booting", null, false)).toBe(false);
  });

  it("labels team and dedicated computers", () => {
    expect(computerLabel("team", "Chief")).toBe("Team computer");
    expect(computerLabel("dedicated", "Chief")).toBe("Chief’s computer");
  });
});

describe("stable screen connection", () => {
  it("treats reminted urls for the same box as the same target", () => {
    const first = signed("view", 1_000_000);
    const remint = signed("view", 2_000_000);
    expect(screenTargetKey(first)).toBe(screenTargetKey(remint));
    expect(shouldReplaceScreenUrl(first, remint, 500_000)).toBe(false);
  });

  it("replaces the iframe only when the box, port, or policy changes", () => {
    const view = signed("view", 2_000_000);
    expect(shouldReplaceScreenUrl(view, signed("control", 2_000_000), 500_000)).toBe(true);
    expect(shouldReplaceScreenUrl(view, signed("view", 2_000_000, 16081), 500_000)).toBe(true);
    expect(shouldReplaceScreenUrl(view, null, 500_000)).toBe(true);
    expect(shouldReplaceScreenUrl(null, view, 500_000)).toBe(true);
  });

  it("refreshes only when the signed url is about to expire", () => {
    const live = signed("view", 1_000_000);
    expect(shouldRefreshScreenUrl(live, 500_000)).toBe(false);
    expect(shouldRefreshScreenUrl(live, 1_000_000 - 30_000)).toBe(true);
    expect(shouldRefreshScreenUrl(null)).toBe(true);
    expect(shouldReplaceScreenUrl(live, signed("view", 3_000_000), 1_000_000 - 30_000)).toBe(true);
  });
});
