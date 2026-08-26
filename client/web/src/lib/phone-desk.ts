export const DESK_SIZE = { width: 1280, height: 800 };

export const TAP_MOVE_PX = 14;
export const TAP_MS = 320;
export const MOVE_SENSITIVITY = 1.7;

export type DeskPoint = { x: number; y: number };

export type DeskGesture = "left-click" | "right-click" | "scroll-up" | "scroll-down" | "none";

export type DeskInput = { kind: string; payload: Record<string, unknown> };

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

const DOM_KEYS: Record<string, string> = {
  Enter: "Return",
  Backspace: "BackSpace",
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
