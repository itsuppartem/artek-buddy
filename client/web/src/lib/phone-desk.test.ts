import { describe, expect, it } from "vitest";
import {
  containBox,
  createDeskInputGate,
  DESK_SIZE,
  deskPointFromPad,
  EXTRA_KEYS,
  enqueueDeskInput,
  gestureFromTouch,
  inputForMove,
  keyFromDomKey,
  keysFromField,
  MOVE_SENSITIVITY,
  moveFromDelta,
  overlayHolderText,
  overlayTitle,
  padStyleFromDesk,
  visualViewportBox,
} from "./phone-desk";
import { shouldUsePhoneShell } from "./phone-shell";

describe("phone desk pad", () => {
  it("keeps the pointer on the 1280×800 box", () => {
    expect(moveFromDelta({ x: 10, y: 10 }, -40, -40)).toEqual({ x: 0, y: 0 });
    expect(moveFromDelta({ x: 640, y: 400 }, 20, -10)).toEqual({
      x: Math.round(640 + 20 * MOVE_SENSITIVITY),
      y: Math.round(400 - 10 * MOVE_SENSITIVITY),
    });
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

  it("maps a tap through the letterboxed 1280×800 guest", () => {
    const fitted = containBox(375, 800);
    expect(fitted.width).toBe(375);
    expect(fitted.top).toBeGreaterThan(100);
    const pad = { left: 0, top: 0, width: 375, height: 800 };
    const mid = deskPointFromPad(187.5, fitted.top + fitted.height / 2, pad);
    expect(mid.x).toBeCloseTo(640, 0);
    expect(mid.y).toBeCloseTo(400, 0);
    const style = padStyleFromDesk({ x: 640, y: 400 }, { width: 375, height: 800 });
    expect(style.left).toBeCloseTo(187.5, 0);
    expect(style.top).toBeCloseTo(fitted.top + fitted.height / 2, 0);
  });

  it("keeps the overlay on the visible viewport when the phone keyboard is up", () => {
    expect(visualViewportBox(812, null)).toEqual({ top: 0, height: 812 });
    expect(visualViewportBox(812, { height: 420, offsetTop: 0 })).toEqual({
      top: 0,
      height: 420,
    });
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
    expect(keysFromField("", "привет")).toEqual([
      { kind: "clipboard", payload: { text: "привет" } },
    ]);
    expect(keysFromField("hello", "hel")).toEqual([
      { kind: "key", payload: { key: "BackSpace" } },
      { kind: "key", payload: { key: "BackSpace" } },
    ]);
  });

  it("maps the phone keyboard specials to xdotool names", () => {
    expect(keyFromDomKey("Enter")).toEqual({ kind: "key", payload: { key: "Return" } });
    expect(keyFromDomKey("Backspace")).toEqual({ kind: "key", payload: { key: "BackSpace" } });
    expect(keyFromDomKey("Delete")).toEqual({ kind: "key", payload: { key: "Delete" } });
    expect(keyFromDomKey("Escape")).toEqual({ kind: "key", payload: { key: "Escape" } });
    expect(keyFromDomKey("ArrowLeft")).toEqual({ kind: "key", payload: { key: "Left" } });
    expect(keyFromDomKey("a")).toBeNull();
    expect(EXTRA_KEYS.map((item) => item.key)).toEqual([
      "Escape",
      "Tab",
      "Enter",
      "Backspace",
      "Delete",
      "ArrowUp",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
    ]);
  });
});

describe("phone desk input gate", () => {
  const click = {
    kind: "click",
    payload: { type: "click", x: 40, y: 40, button: 1 },
  };
  const typeHello = { kind: "clipboard", payload: { text: "hello" } };

  it("keeps only the latest pointer move in the queue", () => {
    expect(enqueueDeskInput([inputForMove({ x: 1, y: 1 })], inputForMove({ x: 9, y: 9 }))).toEqual([
      inputForMove({ x: 9, y: 9 }),
    ]);
  });

  it("does not drop a click or typed keys behind a move", () => {
    expect(enqueueDeskInput([inputForMove({ x: 1, y: 1 })], click)).toEqual([
      inputForMove({ x: 1, y: 1 }),
      click,
    ]);
    expect(enqueueDeskInput([click], inputForMove({ x: 2, y: 2 }))).toEqual([
      click,
      inputForMove({ x: 2, y: 2 }),
    ]);
    expect(enqueueDeskInput([inputForMove({ x: 1, y: 1 })], typeHello)).toEqual([
      inputForMove({ x: 1, y: 1 }),
      typeHello,
    ]);
  });

  it("sends the latest move after an in-flight send, not every pad sample", async () => {
    const sent: { x: unknown }[] = [];
    let releaseFirst!: () => void;
    const first = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    let started = 0;
    const push = createDeskInputGate(async (input) => {
      started += 1;
      sent.push({ x: input.payload.x });
      if (started === 1) await first;
    });
    push(inputForMove({ x: 1, y: 1 }));
    push(inputForMove({ x: 2, y: 2 }));
    push(inputForMove({ x: 3, y: 3 }));
    await Promise.resolve();
    expect(sent).toEqual([{ x: 1 }]);
    releaseFirst();
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
    expect(sent).toEqual([{ x: 1 }, { x: 3 }]);
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
