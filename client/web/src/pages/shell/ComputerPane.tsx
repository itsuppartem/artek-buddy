import type { RefObject, SyntheticEvent } from "react";
import {
  computerLabel,
  computerPaneState,
  embeddableScreenUrl,
  previewPointerEvents,
  screenIframeSandbox,
  screenTargetKey,
} from "../../lib/screen";
import type { Bot, ComputerStatus } from "../../types";
import { Button } from "../../ui/button";
import { MemoryPanel } from "./MemoryPanel";
import { RoutinesPanel } from "./RoutinesPanel";

export function ComputerPane({
  bot,
  computer,
  screenUrl,
  screenError,
  screenEpoch,
  previewFrameRef,
  booting,
  onClose,
  onSettings,
  onOpenFullscreen,
  onTakeControl,
  onRelease,
  onRetryScreen,
  onScreenFrameLoad,
  onLater,
}: {
  bot: Bot;
  computer: ComputerStatus | null;
  screenUrl: string | null;
  screenError: string | null;
  screenEpoch: number;
  previewFrameRef: RefObject<HTMLIFrameElement | null>;
  booting: boolean;
  onClose: () => void;
  onSettings: () => void;
  onOpenFullscreen: () => void;
  onTakeControl: () => void;
  onRelease: () => void;
  onRetryScreen: () => void;
  onScreenFrameLoad: (event: SyntheticEvent<HTMLIFrameElement>) => void;
  onLater: (text: string) => void;
}) {
  const mode = computer?.mode || bot.computerMode;
  const label = computerLabel(mode, bot.name);
  const preview = embeddableScreenUrl(screenUrl);
  const isRunning = computer?.state === "running";
  const isBooting = booting || computer?.state === "booting";
  const isError = computer?.state === "error";
  const isSleeping = computer?.state === "suspended";
  const heldByOther = Boolean(computer?.busyBotName);
  const paneState = computerPaneState(computer?.state, isBooting);

  return (
    <div>
      <div className="mb-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(48,162,75,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#4ECB71]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#30A24B] shadow-[0_0_6px_rgba(48,162,75,0.8)]" />
              Running
            </span>
          ) : isBooting ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(230,87,7,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#FF8542]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#E65707] animate-pulse" />
              Booting…
            </span>
          ) : isError ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(224,49,49,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#FA5252]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#E03131]" />
              Error
            </span>
          ) : isSleeping ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-[rgba(230,87,7,0.14)] px-2.5 py-0.5 text-[12px] font-medium text-[#FF8542]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#E65707]" />
              Sleeping
            </span>
          ) : (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-[#1E1E22] px-2.5 py-0.5 text-[12px] font-medium text-[#85858A]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#4E4E54]" />
              Offline
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[#85858A]">
          <button
            type="button"
            onClick={onSettings}
            className="rounded p-1 hover:text-[#ECECEE] transition-colors"
            title="Settings"
          >
            ⚙
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 hover:text-[#ECECEE] transition-colors"
            title="Close panel"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="group relative aspect-[16/10] w-full overflow-hidden rounded-[14px] border border-[#232326] bg-[#0E0E10]">
        {!heldByOther && preview ? (
          <>
            <iframe
              ref={previewFrameRef}
              key={`${screenTargetKey(preview) ?? "preview"}-${screenEpoch}`}
              data-testid="computer-preview"
              title="Computer preview"
              src={preview}
              sandbox={screenIframeSandbox(preview)}
              className="pointer-events-none h-full w-full border-0 bg-black"
              allow="clipboard-read; clipboard-write"
              style={{ pointerEvents: previewPointerEvents() }}
              onLoad={onScreenFrameLoad}
            />
            {screenError ? (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-[#0E0E10] px-6 text-center">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#3A3A40] border-t-[#30A24B]" />
                <span className="text-[13px] font-medium text-[#ECECEE]">{screenError}</span>
                <Button type="button" variant="outline" size="sm" onClick={onRetryScreen}>
                  Retry
                </Button>
              </div>
            ) : (
              <button
                type="button"
                className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity duration-150 group-hover:opacity-100 cursor-pointer"
                onClick={onOpenFullscreen}
                aria-label="Open computer fullscreen"
              >
                <span className="flex items-center gap-1.5 rounded-lg border border-[#303036] bg-[#161619]/90 px-3 py-1.5 text-[13px] font-medium text-[#ECECEE] shadow-lg backdrop-blur-sm">
                  Open screen ↗
                </span>
              </button>
            )}
          </>
        ) : !heldByOther && isRunning ? (
          <button
            type="button"
            data-testid="computer-preview"
            aria-label="Open computer fullscreen"
            onClick={onOpenFullscreen}
            className="grid h-full w-full place-items-center px-6 text-center cursor-pointer"
          >
            <div className="flex flex-col items-center gap-2 text-[#85858A]">
              {screenError ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#3A3A40] border-t-[#30A24B]" />
              ) : null}
              <span
                data-testid={screenError ? "computer-connecting" : "computer-running"}
                className="text-[13px] font-medium text-[#ECECEE]"
              >
                {screenError || "Desktop is running"}
              </span>
              {screenError ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={(event) => {
                    event.stopPropagation();
                    onRetryScreen();
                  }}
                >
                  Retry
                </Button>
              ) : null}
            </div>
          </button>
        ) : (
          <button
            type="button"
            data-testid="computer-start"
            disabled={Boolean(computer?.busyBotName)}
            className="grid h-full w-full place-items-center px-6 text-center cursor-pointer disabled:cursor-not-allowed"
            onClick={() => {
              if (computer?.busyBotName) return;
              if (isRunning) onOpenFullscreen();
              else if (isSleeping) onTakeControl();
              else onTakeControl();
            }}
          >
            {isBooting ? (
              <div className="flex flex-col items-center gap-2 text-[#A0A0A6]">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#3A3A40] border-t-[#E65707]" />
                <span className="text-[13px] font-medium">Starting desktop…</span>
              </div>
            ) : computer?.busyBotName ? (
              <div className="flex flex-col items-center gap-1 text-[#85858A]">
                <span className="text-[14px] font-medium text-[#ECECEE]">
                  {computer.busyBotName} is using the computer
                </span>
              </div>
            ) : isError ? (
              <div className="flex flex-col items-center gap-1 text-[#FA5252]">
                <span className="text-[13.5px] font-medium">Failed to start</span>
                <span className="text-[12px] text-[#85858A]">Click to retry</span>
              </div>
            ) : isSleeping ? (
              <div className="flex flex-col items-center gap-2 text-[#85858A]">
                <svg
                  width="26"
                  height="26"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-[#4E4E54]"
                >
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                  <line x1="8" y1="21" x2="16" y2="21"></line>
                  <line x1="12" y1="17" x2="12" y2="21"></line>
                </svg>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-medium text-[#ECECEE]">{label}</span>
                  <span className="text-[11.5px] text-[#6C6C70]">Sleeping • Click to start</span>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-[#85858A]">
                <svg
                  width="26"
                  height="26"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-[#4E4E54]"
                >
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                  <line x1="8" y1="21" x2="16" y2="21"></line>
                  <line x1="12" y1="17" x2="12" y2="21"></line>
                </svg>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-medium text-[#ECECEE]">{label}</span>
                  <span className="text-[11.5px] text-[#6C6C70]">Offline • Click to start</span>
                </div>
              </div>
            )}
          </button>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span data-testid="computer-label" data-mode={mode} className="text-[13px] text-[#85858A]">
          {computer?.busyBotName
            ? `${computer.busyBotName} is using it`
            : computer?.controlHolder === "user"
              ? "You have control"
              : label}
        </span>
        <div className="flex items-center gap-2">
          {isRunning && !heldByOther ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onOpenFullscreen}
              className="text-[13px] text-[#ECECEE]"
            >
              Open screen
            </Button>
          ) : null}
          {computer?.controlHolder === "user" ? (
            <Button type="button" variant="outline" size="sm" onClick={onRelease}>
              Release
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={Boolean(computer?.busyBotName)}
              onClick={onTakeControl}
            >
              Take control
            </Button>
          )}
        </div>
      </div>
      <MemoryPanel botId={bot.id} onLater={onLater} />
      <RoutinesPanel botId={bot.id} onLater={onLater} />
    </div>
  );
}
