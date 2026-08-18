import { describe, expect, it } from "vitest";
import {
  computerLabel,
  computerModeHint,
  embeddableScreenUrl,
  isScreenFailureDocument,
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

const FAR = 4_000_000_000_000;
const SOON = 1_700_000_000_000;

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
    expect(shouldAutoBoot("error", null, true)).toBe(false);
    expect(shouldAutoBoot("stopped", "/novnc/x", true)).toBe(false);
  });

  it("labels team and dedicated computers", () => {
    expect(computerLabel("team", "Chief")).toBe("Team computer");
    expect(computerLabel("dedicated", "Chief")).toBe("Chief’s computer");
  });

  it("explains that Private is a separate desktop", () => {
    expect(computerModeHint("team")).toMatch(/share one Linux desktop/);
    expect(computerModeHint("dedicated")).toMatch(/own Linux container/);
  });
});

describe("stable screen connection", () => {
  it("treats reminted urls for the same box as the same target", () => {
    const first = signed("view", SOON);
    const remint = signed("view", FAR);
    expect(screenTargetKey(first)).toBe(screenTargetKey(remint));
    expect(shouldReplaceScreenUrl(first, remint, SOON - 600_000)).toBe(false);
  });

  it("replaces the iframe only when the box, port, or policy changes", () => {
    const view = signed("view", FAR);
    expect(shouldReplaceScreenUrl(view, signed("control", FAR), SOON)).toBe(true);
    expect(shouldReplaceScreenUrl(view, signed("view", FAR, 16081), SOON)).toBe(true);
    expect(shouldReplaceScreenUrl(view, null, SOON)).toBe(true);
    expect(shouldReplaceScreenUrl(null, view, SOON)).toBe(true);
  });

  it("refreshes only when the signed url is about to expire", () => {
    const live = signed("view", SOON);
    expect(shouldRefreshScreenUrl(live, SOON - 600_000)).toBe(false);
    expect(shouldRefreshScreenUrl(live, SOON - 30_000)).toBe(true);
    expect(shouldRefreshScreenUrl(null)).toBe(true);
    expect(shouldReplaceScreenUrl(live, signed("view", FAR), SOON - 30_000)).toBe(true);
  });

  it("detects a 502 JSON page in the preview iframe", () => {
    expect(isScreenFailureDocument('{"detail":"screen unreachable"}')).toBe(true);
    expect(isScreenFailureDocument("Desktop is starting...")).toBe(true);
    expect(isScreenFailureDocument("<canvas id=screen>")).toBe(false);
  });

  it("keeps a live /novnc/ iframe even if the signature is not parsed", () => {
    const loose = "/novnc/abc/16080/view/1.sig/embed.html";
    expect(screenTargetKey(loose)).toBe("abc/16080/view");
    expect(shouldRefreshScreenUrl(loose)).toBe(false);
    expect(shouldReplaceScreenUrl(loose, signed("view", FAR), 1_000)).toBe(false);
  });
});
