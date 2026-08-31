export const DESK_SIZE = { width: 1280, height: 800 };

export const TAP_MOVE_PX = 14;
export const TAP_MS = 320;
export const MOVE_SENSITIVITY = 1.7;

export type DeskPoint = { x: number; y: number };

export type DeskGesture = "left-click" | "right-click" | "scroll-up" | "scroll-down" | "none";

export type DeskInput = { kind: string; payload: Record<string, unknown> };

export function containBox(
  frameW: number,
  frameH: number,
  contentW = DESK_SIZE.width,
  contentH = DESK_SIZE.height,
): { scale: number; width: number; height: number; left: number; top: number } {
  const scale = Math.min(frameW / contentW, frameH / contentH);
  const width = contentW * scale;
  const height = contentH * scale;
  return {
    scale,
    width,
    height,
    left: (frameW - width) / 2,
    top: (frameH - height) / 2,
  };
}

export function deskPointFromPad(
  clientX: number,
  clientY: number,
  pad: { left: number; top: number; width: number; height: number },
): DeskPoint {
  const box = containBox(pad.width, pad.height);
  return clampDeskPoint(
    (clientX - pad.left - box.left) / box.scale,
    (clientY - pad.top - box.top) / box.scale,
  );
}

export function padStyleFromDesk(
  point: DeskPoint,
  pad: { width: number; height: number },
): { left: number; top: number } {
  const box = containBox(pad.width, pad.height);
  return {
    left: box.left + point.x * box.scale,
    top: box.top + point.y * box.scale,
  };
}

export function visualViewportBox(
  innerHeight: number,
  view: { height: number; offsetTop: number } | null,
): { top: number; height: number } {
  if (!view) return { top: 0, height: innerHeight };
  return { top: view.offsetTop, height: view.height };
}

export function clampDeskPoint(x: number, y: number): DeskPoint {
  return {
    x: Math.max(0, Math.min(DESK_SIZE.width - 1, Math.round(x))),
    y: Math.max(0, Math.min(DESK_SIZE.height - 1, Math.round(y))),
  };
}

export function moveFromDelta(
  pos: DeskPoint,
  dx: number,
  dy: number,
  sensitivity = MOVE_SENSITIVITY,
): DeskPoint {
  return clampDeskPoint(pos.x + dx * sensitivity, pos.y + dy * sensitivity);
}

export function gestureFromTouch(input: {
  maxFingers: number;
  totalMovePx: number;
  durationMs: number;
  dy?: number;
}): DeskGesture {
  const tap = input.totalMovePx < TAP_MOVE_PX && input.durationMs <= TAP_MS;
  if (input.maxFingers >= 2 && tap) return "right-click";
  if (input.maxFingers === 1 && tap) return "left-click";
  if (input.maxFingers >= 2 && Math.abs(input.dy || 0) >= TAP_MOVE_PX) {
    return (input.dy || 0) < 0 ? "scroll-up" : "scroll-down";
  }
  return "none";
}

export function inputForGesture(gesture: DeskGesture, pos: DeskPoint): DeskInput | null {
  if (gesture === "left-click") {
    return { kind: "click", payload: { type: "click", x: pos.x, y: pos.y, button: 1 } };
  }
  if (gesture === "right-click") {
    return { kind: "click", payload: { type: "click", x: pos.x, y: pos.y, button: 3 } };
  }
  if (gesture === "scroll-up" || gesture === "scroll-down") {
    return {
      kind: "click",
      payload: { type: "scroll", direction: gesture === "scroll-up" ? "up" : "down", clicks: 3 },
    };
  }
  return null;
}

export function inputForMove(pos: DeskPoint): DeskInput {
  return { kind: "click", payload: { type: "move", x: pos.x, y: pos.y } };
}

export function keysFromField(prev: string, next: string): DeskInput[] {
  if (next === prev) return [];
  if (next.length > prev.length && next.startsWith(prev)) {
    return [{ kind: "clipboard", payload: { text: next.slice(prev.length) } }];
  }
  if (next.length < prev.length && prev.startsWith(next)) {
    return Array.from({ length: prev.length - next.length }, () => ({
      kind: "key",
      payload: { key: "BackSpace" },
    }));
  }
  return [{ kind: "clipboard", payload: { text: next } }];
}

export const EXTRA_KEYS = [
  { label: "Esc", key: "Escape" },
  { label: "Tab", key: "Tab" },
  { label: "Enter", key: "Enter" },
  { label: "Bksp", key: "Backspace" },
  { label: "Del", key: "Delete" },
  { label: "↑", key: "ArrowUp" },
  { label: "↓", key: "ArrowDown" },
  { label: "←", key: "ArrowLeft" },
  { label: "→", key: "ArrowRight" },
] as const;

const DOM_KEYS: Record<string, string> = {
  Enter: "Return",
  Backspace: "BackSpace",
  Delete: "Delete",
  Escape: "Escape",
  Tab: "Tab",
  ArrowUp: "Up",
  ArrowDown: "Down",
  ArrowLeft: "Left",
  ArrowRight: "Right",
};

export function keyFromDomKey(key: string): DeskInput | null {
  const mapped = DOM_KEYS[key];
  if (!mapped) return null;
  return { kind: "key", payload: { key: mapped } };
}

export function capsLockDeskInput(
  key: string,
  inControl: boolean,
  guestKeyboard: boolean,
): DeskInput | null {
  if (key !== "CapsLock" || !inControl || guestKeyboard) return null;
  return { kind: "key", payload: { key: "Caps_Lock" } };
}

export function overlayTitle(
  mode: string | null | undefined,
  name: string,
  compact: boolean,
): string {
  if (!compact) {
    return mode === "dedicated" ? `${name}’s computer` : "Team computer";
  }
  return mode === "dedicated" ? name : "Team";
}

export function overlayHolderText(compact: boolean): string {
  return compact
    ? "You have control"
    : "You have control · returns to the bot after two idle minutes";
}

export function isDeskPointerMove(input: DeskInput): boolean {
  return input.kind === "click" && input.payload.type === "move";
}

export function enqueueDeskInput(queue: DeskInput[], incoming: DeskInput): DeskInput[] {
  if (isDeskPointerMove(incoming)) {
    const last = queue[queue.length - 1];
    if (last && isDeskPointerMove(last)) {
      return [...queue.slice(0, -1), incoming];
    }
  }
  return [...queue, incoming];
}

export function createDeskInputGate(
  send: (input: DeskInput) => Promise<unknown>,
): (input: DeskInput) => void {
  let queue: DeskInput[] = [];
  let busy = false;

  async function drain(): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      while (queue.length > 0) {
        const next = queue.shift();
        if (!next) break;
        try {
          await send(next);
        } catch {
          // A failed move must not stall later clicks or typed keys.
        }
      }
    } finally {
      busy = false;
    }
    if (queue.length > 0) await drain();
  }

  return (input: DeskInput) => {
    queue = enqueueDeskInput(queue, input);
    void drain();
  };
}
