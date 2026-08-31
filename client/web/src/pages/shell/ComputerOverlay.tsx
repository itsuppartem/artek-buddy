import { type RefObject, type SyntheticEvent, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import {
  capsLockDeskInput,
  createDeskInputGate,
  type DeskInput,
  overlayHolderText,
  overlayTitle,
  visualViewportBox,
} from "../../lib/phone-desk";
import {
  computerLabel,
  embeddableScreenUrl,
  overlayDisplayUrl,
  overlayPendingUrl,
  overlayPointerEvents,
  overlayWaitingLabel,
  screenIframeSandbox,
  shouldReportOwnerActivity,
} from "../../lib/screen";
import type { Bot, ComputerStatus } from "../../types";
import { BotAvatar } from "../../ui/bot-avatar";
import { Button } from "../../ui/button";
import { PhoneDeskPad } from "./PhoneDeskPad";

function useOverlayViewport(enabled: boolean) {
  const [box, setBox] = useState(() =>
    typeof window === "undefined"
      ? { top: 0, height: 0 }
      : visualViewportBox(window.innerHeight, window.visualViewport),
  );
  useEffect(() => {
    if (!enabled) return;
    const apply = () => {
      setBox(visualViewportBox(window.innerHeight, window.visualViewport));
    };
    apply();
    window.visualViewport?.addEventListener("resize", apply);
    window.visualViewport?.addEventListener("scroll", apply);
    window.addEventListener("resize", apply);
    return () => {
      window.visualViewport?.removeEventListener("resize", apply);
      window.visualViewport?.removeEventListener("scroll", apply);
      window.removeEventListener("resize", apply);
    };
  }, [enabled]);
  return box;
}

export function ComputerOverlay({
  booting,
  open,
  bot,
  computer,
  screenUrl,
  screenError,
  screenEpoch,
  overlayFrameRef,
  onRelease,
  onTakeControl,
  onClose,
  onRetry,
  onScreenFrameLoad,
  onScreenError,
  phone,
}: {
  booting: boolean;
  open: boolean;
  bot: Bot | undefined;
  computer: ComputerStatus | null;
  screenUrl: string | null;
  screenError: string | null;
  screenEpoch: number;
  overlayFrameRef: RefObject<HTMLIFrameElement | null>;
  onRelease: () => void;
  onTakeControl: () => void;
  onClose: () => void;
  onRetry: () => void;
  onScreenFrameLoad: (event: SyntheticEvent<HTMLIFrameElement>) => void;
  onScreenError: (message: string) => void;
  phone: boolean;
}) {
  const lastActivityMs = useRef(0);
  const deskBotIdRef = useRef(bot?.id ?? "");
  deskBotIdRef.current = bot?.id ?? "";
  const deskGateRef = useRef<((input: DeskInput) => void) | null>(null);
  if (deskGateRef.current === null) {
    deskGateRef.current = createDeskInputGate((input) =>
      api.computer.input(deskBotIdRef.current, input),
    );
  }
  const [frameReady, setFrameReady] = useState(0);
  const [keysOpen, setKeysOpen] = useState(false);
  const nextUrl = embeddableScreenUrl(screenUrl);
  const [shownUrl, setShownUrl] = useState<string | null>(null);
  const view = useOverlayViewport(phone && open);

  useEffect(() => {
    if (!open || !nextUrl) setShownUrl(null);
  }, [open, nextUrl]);

  function reportOwnerActivity() {
    if (computer?.controlHolder !== "user" || !bot) return;
    const now = Date.now();
    if (!shouldReportOwnerActivity(lastActivityMs.current, now)) return;
    lastActivityMs.current = now;
    void api.computer.input(bot.id, { kind: "activity", payload: {} });
  }

  useEffect(() => {
    if (!open || computer?.controlHolder !== "user") return;
    const doc = overlayFrameRef.current?.contentDocument;
    if (!doc) return;
    const onAct = () => reportOwnerActivity();
    doc.addEventListener("pointerdown", onAct);
    doc.addEventListener("pointermove", onAct);
    doc.addEventListener("keydown", onAct);
    doc.addEventListener("wheel", onAct, { passive: true });
    return () => {
      doc.removeEventListener("pointerdown", onAct);
      doc.removeEventListener("pointermove", onAct);
      doc.removeEventListener("keydown", onAct);
      doc.removeEventListener("wheel", onAct);
    };
  }, [open, computer?.controlHolder, overlayFrameRef, screenEpoch, screenUrl, frameReady]);

  useEffect(() => {
    if (!open || computer?.controlHolder !== "user") return;
    const guestKeyboard = Boolean(embeddableScreenUrl(screenUrl));
    const onKey = (event: KeyboardEvent) => {
      const input = capsLockDeskInput(event.key, true, guestKeyboard);
      if (!input) return;
      deskGateRef.current?.(input);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, computer?.controlHolder, screenUrl]);

  if (!open || !bot) return null;

  function sendDeskInput(input: DeskInput) {
    reportOwnerActivity();
    deskGateRef.current?.(input);
  }

  const inControl = computer?.controlHolder === "user";
  const title = overlayTitle(computer?.mode || bot.computerMode, bot.name, phone);
  const displayUrl = overlayDisplayUrl(shownUrl, nextUrl);
  const pendingUrl = overlayPendingUrl(shownUrl, nextUrl);
  const waiting = overlayWaitingLabel({
    booting,
    state: computer?.state,
    hasFrame: Boolean(shownUrl),
    hasUrl: Boolean(nextUrl),
  });

  function markGuestFrame(url: string, event: SyntheticEvent<HTMLIFrameElement>) {
    onScreenFrameLoad(event);
    setShownUrl(url);
    setFrameReady((value) => value + 1);
  }

  return (
    <div
      className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-ink select-none"
      data-testid="computer-overlay"
      data-phone-desk={phone ? "1" : "0"}
      style={
        phone && view.height > 0
          ? { top: view.top, height: view.height, bottom: "auto" }
          : undefined
      }
      tabIndex={0}
      onPointerDown={reportOwnerActivity}
      onPointerMove={reportOwnerActivity}
      onWheel={reportOwnerActivity}
      onKeyDown={reportOwnerActivity}
    >
      <div
        className={`relative z-30 flex items-center justify-between border-b border-hairline ${
          phone ? "gap-2 px-3 py-2" : "gap-4 px-[18px] py-3.5"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2">
          <BotAvatar color={bot.color} size={phone ? 24 : 28} />
          <span
            className={`min-w-0 truncate font-medium text-paper ${
              phone ? "text-[14px]" : "text-[15.5px]"
            }`}
          >
            {title}
          </span>
          {inControl ? (
            <span
              data-testid="computer-overlay-holder"
              className={`shrink-0 rounded-full bg-sage-bg text-sage ${
                phone ? "px-2 py-0.5 text-[12px]" : "px-[11px] py-1 text-[13px]"
              }`}
            >
              {overlayHolderText(phone)}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {phone && inControl ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="phone-desk-keyboard"
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => setKeysOpen((openKeys) => !openKeys)}
            >
              Keyboard
            </Button>
          ) : null}
          {inControl ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onPointerDown={(event) => event.preventDefault()}
              onClick={onRelease}
            >
              Release
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onPointerDown={(event) => event.preventDefault()}
              onClick={onTakeControl}
            >
              Take control
            </Button>
          )}
          <button
            type="button"
            className="min-h-11 min-w-11 text-[16px] text-mute hover:text-paper"
            aria-label="Close computer"
            onPointerDown={(event) => {
              event.preventDefault();
              onClose();
            }}
          >
            ✕
          </button>
        </div>
      </div>
      {phone && !keysOpen ? (
        <p className="phone-desk-hint shrink-0 select-none touch-none px-3 py-1 text-[12px] text-mute">
          Turn the phone sideways to see more. Drag to move the pointer. Tap is left click; two
          fingers is right click.
        </p>
      ) : null}
      <div className="relative min-h-0 flex-1 bg-ink" data-testid="computer-overlay-screen">
        {displayUrl ? (
          <>
            <iframe
              ref={pendingUrl ? undefined : overlayFrameRef}
              key={`${displayUrl}-${screenEpoch}`}
              title="Bot screen"
              src={displayUrl}
              sandbox={screenIframeSandbox(displayUrl)}
              className="absolute inset-0 z-0 h-full w-full border-0 bg-ink"
              allow="clipboard-read; clipboard-write; fullscreen"
              style={{
                pointerEvents: phone ? "none" : overlayPointerEvents(computer?.controlHolder),
              }}
              onLoad={(event) => markGuestFrame(displayUrl, event)}
              onError={() => onScreenError("Screen preview failed to load")}
            />
            {pendingUrl ? (
              <iframe
                ref={overlayFrameRef}
                key={`${pendingUrl}-${screenEpoch}`}
                title="Bot screen (next)"
                src={pendingUrl}
                sandbox={screenIframeSandbox(pendingUrl)}
                className="pointer-events-none absolute inset-0 z-0 h-full w-full border-0 bg-ink opacity-0"
                allow="clipboard-read; clipboard-write; fullscreen"
                onLoad={(event) => markGuestFrame(pendingUrl, event)}
                onError={() => onScreenError("Screen preview failed to load")}
              />
            ) : null}
            {waiting ? (
              <div
                data-testid="computer-overlay-waiting"
                className="absolute inset-0 z-20 grid place-items-center bg-ink/85 px-6 text-center text-sm text-paper"
              >
                {waiting}
              </div>
            ) : null}
            {screenError ? (
              <div className="absolute inset-0 z-10 grid place-items-center gap-3 bg-ink text-sm text-mute">
                <div>{screenError}</div>
                <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                  Retry
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <div className="absolute inset-0 grid place-items-center gap-3 px-6 text-center text-sm text-mute">
            {waiting ? (
              <div data-testid="computer-overlay-waiting" className="text-paper">
                {waiting}
              </div>
            ) : (
              <div>
                {screenError
                  ? screenError
                  : computer?.state === "running"
                    ? phone
                      ? "Desktop is running. Drag to move the pointer."
                      : "Desktop is running"
                    : computer?.state === "suspended"
                      ? "Computer is asleep"
                      : computerLabel(computer?.mode, bot.name)}
              </div>
            )}
            {screenError ? (
              <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                Retry
              </Button>
            ) : null}
          </div>
        )}
        {phone ? (
          <PhoneDeskPad
            enabled={inControl}
            keysOpen={keysOpen}
            onInput={sendDeskInput}
            onDismissKeys={() => setKeysOpen(false)}
          />
        ) : null}
      </div>
    </div>
  );
}
