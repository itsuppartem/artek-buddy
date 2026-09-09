import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import {
  paneWidthAfterDrag,
  paneWidthAfterKey,
  paneWidthLimits,
  type ResizablePane,
} from "../../lib/pane-resize";

export function PaneResizeHandle({
  pane,
  width,
  defaultWidth,
  onChange,
}: {
  pane: ResizablePane;
  width: number;
  defaultWidth: number;
  onChange: (width: number) => void;
}) {
  const limits = paneWidthLimits(pane);
  const label = pane === "left" ? "Resize work list" : "Resize side panel";

  function startDrag(event: ReactPointerEvent<HTMLHRElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function move(pointerEvent: PointerEvent) {
      onChange(paneWidthAfterDrag(pane, startWidth, pointerEvent.clientX - startX));
    }

    function stop() {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    }

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  }

  function resizeWithKeyboard(event: KeyboardEvent<HTMLHRElement>) {
    const next = paneWidthAfterKey(pane, width, event.key);
    if (next === width) return;
    event.preventDefault();
    onChange(next);
  }

  return (
    <hr
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={limits.min}
      aria-valuemax={limits.max}
      aria-valuenow={width}
      tabIndex={0}
      onPointerDown={startDrag}
      onDoubleClick={() => onChange(defaultWidth)}
      onKeyDown={resizeWithKeyboard}
      className="pane-resize-handle group relative z-20 m-0 h-full w-2 shrink-0 cursor-col-resize touch-none border-0 bg-transparent p-0 focus-visible:outline-none"
    />
  );
}
