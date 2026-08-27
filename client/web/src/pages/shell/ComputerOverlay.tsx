import { type RefObject, type SyntheticEvent, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import {
  type DeskInput,
  overlayHolderText,
  overlayTitle,
  visualViewportBox,
} from "../../lib/phone-desk";
import {
  computerLabel,
  embeddableScreenUrl,
  overlayPointerEvents,
  screenIframeSandbox,
  screenTargetKey,
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
  const [frameReady, setFrameReady] = useState(0);
  const [keysOpen, setKeysOpen] = useState(false);
  const view = useOverlayViewport(phone && open);

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

  if (booting) {
    return (
      <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-[22px] bg-[rgba(4,4,5,.96)]">
        <div className="text-[19px] font-medium text-[#F1F1F2]">
          Booting up{" "}
          {bot ? computerLabel(computer?.mode || bot.computerMode, bot.name) : "computer"}
        </div>
        <div className="h-[5px] w-[min(420px,70%)] overflow-hidden rounded-full bg-[#232327]">
          <div className="h-full w-2/3 rounded-full bg-[#F1F1EF]" />
        </div>
      </div>
    );
  }
  if (!open || !bot) return null;
  const deskBot = bot;

  function sendDeskInput(input: DeskInput) {
    reportOwnerActivity();
    void api.computer.input(deskBot.id, input);
  }

  const inControl = computer?.controlHolder === "user";
  const title = overlayTitle(computer?.mode || bot.computerMode, bot.name, phone);

  return (
    <div
      className="absolute inset-0 z-30 flex flex-col overflow-hidden bg-[#050506] select-none"
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
      onKeyDown={(event) => {
        reportOwnerActivity();
        if (event.key !== "CapsLock" || !inControl) return;
        event.preventDefault();
        void api.computer.input(deskBot.id, { kind: "key", payload: { key: "Caps_Lock" } });
      }}
    >
      <div
        className={`relative z-30 flex items-center justify-between border-b border-[#171719] ${
          phone ? "gap-2 px-3 py-2" : "gap-4 px-[18px] py-3.5"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2">
          <BotAvatar color={bot.color} size={phone ? 24 : 28} />
          <span
            className={`min-w-0 truncate font-medium text-[#ECECEE] ${
              phone ? "text-[14px]" : "text-[15.5px]"
            }`}
          >
            {title}
          </span>
          {inControl ? (
            <span
              data-testid="computer-overlay-holder"
              className={`shrink-0 rounded-full bg-[rgba(48,162,75,.14)] text-[#4ECB71] ${
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
            className="min-h-11 min-w-11 text-[16px] text-[#85858A] hover:text-[#ECECEE]"
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
        <p className="phone-desk-hint shrink-0 select-none touch-none px-3 py-1 text-[12px] text-[#85858A]">
          Turn the phone sideways to see more. Drag to move the pointer. Tap is left click; two
          fingers is right click.
        </p>
      ) : null}
      <div className="relative min-h-0 flex-1 bg-[#0E0E10]" data-testid="computer-overlay-screen">
        {embeddableScreenUrl(screenUrl) ? (
          <>
            <iframe
              ref={overlayFrameRef}
              key={`${screenTargetKey(screenUrl) ?? "screen"}-${screenEpoch}`}
              title="Bot screen"
              src={embeddableScreenUrl(screenUrl) ?? undefined}
              sandbox={screenIframeSandbox(screenUrl)}
              className="absolute inset-0 h-full w-full border-0 bg-black"
              allow="clipboard-read; clipboard-write; fullscreen"
              style={{
                pointerEvents: phone ? "none" : overlayPointerEvents(computer?.controlHolder),
              }}
              onLoad={(event) => {
                onScreenFrameLoad(event);
                setFrameReady((value) => value + 1);
              }}
              onError={() => onScreenError("Screen preview failed to load")}
            />
            {screenError ? (
              <div className="absolute inset-0 z-10 grid place-items-center gap-3 bg-[#0E0E10] text-sm text-[#6C6C70]">
                <div>{screenError}</div>
                <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                  Retry
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <div className="absolute inset-0 grid place-items-center gap-3 px-6 text-center text-sm text-[#6C6C70]">
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
