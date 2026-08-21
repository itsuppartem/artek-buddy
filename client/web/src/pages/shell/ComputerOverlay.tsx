import { type RefObject, type SyntheticEvent } from "react";
import { api } from "../../api";
import {
  computerLabel,
  embeddableScreenUrl,
  overlayPointerEvents,
  screenIframeSandbox,
  screenTargetKey,
} from "../../lib/screen";
import type { Bot, ComputerStatus } from "../../types";
import { BotAvatar } from "../../ui/bot-avatar";
import { Button } from "../../ui/button";

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
}) {
  if (booting) {
    return (
      <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-[22px] bg-[rgba(4,4,5,.96)]">
        <div className="text-[19px] font-medium text-[#F1F1F2]">
          Booting up {bot ? computerLabel(computer?.mode || bot.computerMode, bot.name) : "computer"}
        </div>
        <div className="h-[5px] w-[min(420px,70%)] overflow-hidden rounded-full bg-[#232327]">
          <div className="h-full w-2/3 rounded-full bg-[#F1F1EF]" />
        </div>
      </div>
    );
  }
  if (!open || !bot) return null;
  return (
    <div
      className="absolute inset-0 z-30 flex flex-col bg-[#050506]"
      data-testid="computer-overlay"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key !== "CapsLock" || computer?.controlHolder !== "user") return;
        event.preventDefault();
        void api.computer.input(bot.id, { kind: "key", payload: { key: "Caps_Lock" } });
      }}
    >
      <div className="flex items-center justify-between gap-4 border-b border-[#171719] px-[18px] py-3.5">
        <div className="flex min-w-0 items-center gap-3">
          <BotAvatar color={bot.color} size={28} />
          <span className="truncate text-[15.5px] font-medium text-[#ECECEE]">
            {computerLabel(computer?.mode || bot.computerMode, bot.name)}
          </span>
          {computer?.controlHolder === "user" ? (
            <span
              data-testid="computer-overlay-holder"
              className="rounded-full bg-[rgba(48,162,75,.14)] px-[11px] py-1 text-[13px] text-[#4ECB71]"
            >
              You have control
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {computer?.controlHolder === "user" ? (
            <Button type="button" variant="outline" size="sm" onClick={onRelease}>
              Release
            </Button>
          ) : (
            <Button type="button" variant="outline" size="sm" onClick={onTakeControl}>
              Take control
            </Button>
          )}
          <button
            type="button"
            className="text-[16px] text-[#85858A] hover:text-[#ECECEE]"
            aria-label="Close computer"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1 bg-[#0E0E10]">
        {embeddableScreenUrl(screenUrl) ? (
          <>
            <iframe
              ref={overlayFrameRef}
              key={`${screenTargetKey(screenUrl) ?? "screen"}-${screenEpoch}`}
              title="Bot screen"
              src={embeddableScreenUrl(screenUrl) ?? undefined}
              sandbox={screenIframeSandbox(screenUrl)}
              className="h-full w-full border-0 bg-black"
              allow="clipboard-read; clipboard-write; fullscreen"
              style={{ pointerEvents: overlayPointerEvents(computer?.controlHolder) }}
              onLoad={onScreenFrameLoad}
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
          <div className="grid h-full place-items-center gap-3 text-sm text-[#6C6C70]">
            <div>
              {screenError
                ? screenError
                : computer?.state === "running"
                  ? "Desktop is running"
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
      </div>
    </div>
  );
}
