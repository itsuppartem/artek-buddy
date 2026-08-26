import { type PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from "react";
import {
  DESK_SIZE,
  type DeskInput,
  type DeskPoint,
  deskPointFromPad,
  EXTRA_KEYS,
  gestureFromTouch,
  inputForGesture,
  inputForMove,
  keyFromDomKey,
  keysFromField,
  padStyleFromDesk,
} from "../../lib/phone-desk";

export function PhoneDeskPad({
  enabled,
  keysOpen,
  onInput,
  onDismissKeys,
}: {
  enabled: boolean;
  keysOpen: boolean;
  onInput: (input: DeskInput) => void;
  onDismissKeys: () => void;
}) {
  const padRef = useRef<HTMLDivElement>(null);
  const keysRef = useRef<HTMLInputElement>(null);
  const [field, setField] = useState("");
  const [padSize, setPadSize] = useState({ width: DESK_SIZE.width, height: DESK_SIZE.height });
  const pos = useRef<DeskPoint>({
    x: Math.round(DESK_SIZE.width / 2),
    y: Math.round(DESK_SIZE.height / 2),
  });
  const [dot, setDot] = useState(pos.current);

  useEffect(() => {
    const el = padRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setPadSize({ width: rect.width, height: rect.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const el = padRef.current;
    if (!el) return;
    const stop = (event: TouchEvent) => event.preventDefault();
    el.addEventListener("touchstart", stop, { passive: false });
    return () => el.removeEventListener("touchstart", stop);
  }, []);

  useEffect(() => {
    if (!keysOpen) return;
    keysRef.current?.focus({ preventScroll: true });
  }, [keysOpen]);

  const stroke = useRef({
    pointers: new Map<number, { x: number; y: number }>(),
    start: 0,
    move: 0,
    dy: 0,
    maxFingers: 0,
    lastMoveAt: 0,
  });

  function send(input: DeskInput | null) {
    if (!input || !enabled) return;
    onInput(input);
  }

  function pointFromEvent(event: { clientX: number; clientY: number }): DeskPoint {
    const el = padRef.current;
    if (!el) return pos.current;
    const rect = el.getBoundingClientRect();
    return deskPointFromPad(event.clientX, event.clientY, {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    });
  }

  function place(event: { clientX: number; clientY: number }, report: boolean) {
    pos.current = pointFromEvent(event);
    setDot(pos.current);
    if (report) send(inputForMove(pos.current));
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (!enabled) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const now = Date.now();
    const s = stroke.current;
    if (s.pointers.size === 0) {
      s.start = now;
      s.move = 0;
      s.dy = 0;
      s.maxFingers = 0;
    }
    s.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    s.maxFingers = Math.max(s.maxFingers, s.pointers.size);
    if (s.pointers.size === 1) place(event, true);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!enabled || !stroke.current.pointers.has(event.pointerId)) return;
    event.preventDefault();
    const s = stroke.current;
    const last = s.pointers.get(event.pointerId);
    s.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (s.pointers.size !== 1 || s.maxFingers > 1) {
      if (last) {
        const ddx = event.clientX - last.x;
        const ddy = event.clientY - last.y;
        s.dy += ddy;
        s.move += Math.hypot(ddx, ddy);
      }
      return;
    }
    if (last) s.move += Math.hypot(event.clientX - last.x, event.clientY - last.y);
    const now = Date.now();
    if (now - s.lastMoveAt < 32) {
      place(event, false);
      return;
    }
    s.lastMoveAt = now;
    place(event, true);
  }

  function onPointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (!enabled) return;
    event.preventDefault();
    const s = stroke.current;
    s.pointers.delete(event.pointerId);
    if (s.pointers.size > 0) return;
    send(
      inputForGesture(
        gestureFromTouch({
          maxFingers: s.maxFingers,
          totalMovePx: s.move,
          durationMs: Date.now() - s.start,
          dy: s.dy,
        }),
        pos.current,
      ),
    );
    s.maxFingers = 0;
    s.move = 0;
    s.dy = 0;
  }

  const cursor = padStyleFromDesk(dot, padSize);

  return (
    <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
      <div
        ref={padRef}
        data-testid="phone-desk-pad"
        className="absolute inset-0 touch-none"
        style={{ pointerEvents: enabled ? "auto" : "none" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {enabled ? (
          <span
            data-testid="phone-desk-cursor"
            className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-ink bg-tan"
            style={{ left: cursor.left, top: cursor.top }}
          />
        ) : null}
      </div>
      {keysOpen ? (
        <div
          data-testid="phone-desk-key-row"
          className="pointer-events-auto absolute inset-x-0 bottom-0 z-20 flex flex-nowrap gap-1 border-t border-hairline bg-plate px-1.5 py-1"
        >
          {EXTRA_KEYS.map((item) => (
            <button
              key={item.key}
              type="button"
              className="min-h-11 min-w-0 flex-1 rounded-[8px] bg-raised text-[12px] font-medium text-paper"
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => send(keyFromDomKey(item.key))}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
      {keysOpen ? (
        <input
          ref={keysRef}
          data-testid="phone-desk-keys"
          aria-label="Type on the desktop"
          value={field}
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          enterKeyHint="done"
          className="pointer-events-none absolute top-0 left-0 h-px w-px overflow-hidden opacity-0"
          onChange={(event) => {
            const next = event.target.value;
            for (const input of keysFromField(field, next)) send(input);
            setField(next);
          }}
          onKeyDown={(event) => {
            const mapped = keyFromDomKey(event.key);
            if (event.key === "Enter" && mapped) {
              event.preventDefault();
              send(mapped);
              setField("");
            }
          }}
          onBlur={() => onDismissKeys()}
        />
      ) : null}
    </div>
  );
}
