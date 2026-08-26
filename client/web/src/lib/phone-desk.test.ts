import { describe, expect, it } from "vitest";
import {
  DESK_SIZE,
  gestureFromTouch,
  keyFromDomKey,
  keysFromField,
  moveFromDelta,
  overlayHolderText,
  overlayTitle,
} from "./phone-desk";
import { shouldUsePhoneShell } from "./phone-shell";

describe("phone desk pad", () => {
  it("keeps the pointer on the 1280×800 box", () => {
    expect(moveFromDelta({ x: 10, y: 10 }, -40, -40)).toEqual({ x: 0, y: 0 });
    expect(moveFromDelta({ x: 1270, y: 790 }, 80, 80)).toEqual({
      x: DESK_SIZE.width - 1,
      y: DESK_SIZE.height - 1,
    });
  });

  it("treats a short one-finger lift as left click and two fingers as right click", () => {
    expect(gestureFromTouch({ maxFingers: 1, totalMovePx: 4, durationMs: 90 })).toBe("left-click");
    expect(gestureFromTouch({ maxFingers: 2, totalMovePx: 6, durationMs: 80 })).toBe("right-click");
    expect(gestureFromTouch({ maxFingers: 1, totalMovePx: 40, durationMs: 200 })).toBe("none");
  });

  it("scrolls on a two-finger vertical drag", () => {
    expect(gestureFromTouch({ maxFingers: 2, totalMovePx: 36, durationMs: 200, dy: -40 })).toBe(
      "scroll-up",
    );
    expect(gestureFromTouch({ maxFingers: 2, totalMovePx: 36, durationMs: 200, dy: 40 })).toBe(
      "scroll-down",
    );
  });
});

describe("phone desk keys", () => {
  it("types the added run and sends BackSpace for a delete", () => {
    expect(keysFromField("hel", "hello")).toEqual([{ kind: "clipboard", payload: { text: "lo" } }]);
    expect(keysFromField("hello", "hel")).toEqual([
      { kind: "key", payload: { key: "BackSpace" } },
      { kind: "key", payload: { key: "BackSpace" } },
    ]);
  });

  it("maps the phone keyboard specials to xdotool names", () => {
    expect(keyFromDomKey("Enter")).toEqual({ kind: "key", payload: { key: "Return" } });
    expect(keyFromDomKey("Escape")).toEqual({ kind: "key", payload: { key: "Escape" } });
    expect(keyFromDomKey("ArrowLeft")).toEqual({ kind: "key", payload: { key: "Left" } });
    expect(keyFromDomKey("a")).toBeNull();
  });
});

describe("phone overlay chrome", () => {
  it("shortens the title and holder on a narrow overlay", () => {
    expect(overlayTitle("shared", "test", true)).toBe("Team");
    expect(overlayTitle("dedicated", "test", true)).toBe("test");
    expect(overlayHolderText(true)).toBe("You have control");
    expect(overlayHolderText(false)).toContain("two idle minutes");
  });

  it("keeps the stacked shell in landscape iPhone 11 Pro", () => {
    expect(shouldUsePhoneShell(812, 375)).toBe(true);
    expect(shouldUsePhoneShell(375, 812)).toBe(true);
    expect(shouldUsePhoneShell(1280, 720)).toBe(false);
    expect(shouldUsePhoneShell(1280, 800)).toBe(false);
  });
});
