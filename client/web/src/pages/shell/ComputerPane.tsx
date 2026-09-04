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
import { IconClose, IconComputer } from "../../ui/icons";

export function ComputerPane({
  bot,
  computer,
  screenUrl,
  screenError,
  screenEpoch,
  previewFrameRef,
  booting,
  onClose,
  onOpenFullscreen,
  onStart,
  onTakeControl,
  onRelease,
  onRetryScreen,
  onScreenFrameLoad,
}: {
  bot: Bot;
  computer: ComputerStatus | null;
  screenUrl: string | null;
  screenError: string | null;
  screenEpoch: number;
  previewFrameRef: RefObject<HTMLIFrameElement | null>;
  booting: boolean;
  onClose: () => void;
  onOpenFullscreen: () => void;
  onStart: () => void;
  onTakeControl: () => void;
  onRelease: () => void;
  onRetryScreen: () => void;
  onScreenFrameLoad: (event: SyntheticEvent<HTMLIFrameElement>) => void;
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
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-sage-bg px-2.5 py-0.5 text-[12px] font-medium text-sage"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-sage" />
              Running
            </span>
          ) : isBooting ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-raised px-2.5 py-0.5 text-[12px] font-medium text-tan"
            >
              <span className="ab-pulse h-1.5 w-1.5 rounded-full bg-tan" />
              Booting…
            </span>
          ) : isError ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-danger-bg px-2.5 py-0.5 text-[12px] font-medium text-danger"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-danger" />
              Error
            </span>
          ) : isSleeping ? (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-sage-bg px-2.5 py-0.5 text-[12px] font-medium text-sage"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-sage" />
              Sleeping
            </span>
          ) : (
            <span
              data-testid="computer-state"
              data-state={paneState}
              className="inline-flex items-center gap-1.5 rounded-full bg-raised px-2.5 py-0.5 text-[12px] font-medium text-mute"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-mute" />
              Offline
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-mute">
          <button
            type="button"
            onClick={onClose}
            title="Close panel"
            className="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[13px] text-paper hover:bg-raised"
          >
            <IconClose />
            Close
          </button>
        </div>
      </div>

      <div className="group relative aspect-[16/10] w-full overflow-hidden rounded-[8px] border border-hairline bg-ink shadow-[inset_0_0_0_2px_var(--color-tan)]">
        {!heldByOther && isRunning && preview ? (
          <>
            <iframe
              ref={previewFrameRef}
              key={`${screenTargetKey(preview) ?? "preview"}-${screenEpoch}`}
              data-testid="computer-preview"
              title="Computer preview"
              src={preview}
              sandbox={screenIframeSandbox(preview)}
              className="pointer-events-none h-full w-full border-0 bg-ink"
              allow="clipboard-read; clipboard-write"
              style={{ pointerEvents: previewPointerEvents() }}
              onLoad={onScreenFrameLoad}
            />
            <p className="pointer-events-none absolute top-2 left-2 rounded bg-ink/80 px-2 py-0.5 text-[11px] text-paper">
              Preview · view only
            </p>
            {screenError ? (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-ink px-6 text-center">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-hairline border-t-sage" />
                <span className="text-[13px] font-medium text-paper">{screenError}</span>
                <Button type="button" variant="outline" size="sm" onClick={onRetryScreen}>
                  Retry
                </Button>
              </div>
            ) : (
              <button
                type="button"
                className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity duration-150 group-hover:opacity-100"
                onClick={onOpenFullscreen}
                aria-label="Open computer fullscreen"
              >
                <span className="flex items-center gap-1.5 rounded-lg border border-hairline bg-plate/90 px-3 py-1.5 text-[13px] font-medium text-paper">
                  Open screen
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
            className="grid h-full w-full place-items-center px-6 text-center"
          >
            <div className="flex flex-col items-center gap-2 text-mute">
              {screenError ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-hairline border-t-sage" />
              ) : null}
              <span
                data-testid={screenError ? "computer-connecting" : "computer-running"}
                className="text-[13px] font-medium text-paper"
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
            className="grid h-full w-full place-items-center px-6 text-center disabled:cursor-not-allowed"
            onClick={() => {
              if (computer?.busyBotName) return;
              if (isRunning) onOpenFullscreen();
              else onStart();
            }}
          >
            {isBooting ? (
              <div className="flex flex-col items-center gap-2 text-mute">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-hairline border-t-tan" />
                <span className="text-[13px] font-medium">Starting desktop…</span>
              </div>
            ) : computer?.busyBotName ? (
              <div className="flex flex-col items-center gap-1 text-mute">
                <span className="text-[14px] font-medium text-paper">
                  {computer.busyBotName} is using the computer
                </span>
              </div>
            ) : isError ? (
              <div className="flex flex-col items-center gap-1 text-danger">
                <span className="text-[13.5px] font-medium">Failed to start</span>
                <span className="text-[12px] text-mute">Click to retry</span>
              </div>
            ) : isSleeping ? (
              <div className="flex flex-col items-center gap-2 text-sage">
                <IconComputer />
                <div className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-medium text-paper">{label}</span>
                  <span className="text-[11.5px] text-sage">Sleeping • Click to start</span>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-mute">
                <IconComputer />
                <div className="flex flex-col gap-0.5">
                  <span className="text-[13px] font-medium text-paper">{label}</span>
                  <span className="text-[11.5px] text-mute">Offline • Click to start</span>
                </div>
              </div>
            )}
          </button>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span data-testid="computer-label" data-mode={mode} className="text-[13px] text-mute">
          {computer?.busyBotName
            ? `${computer.busyBotName} is using it`
            : computer?.controlHolder === "user"
              ? "You have control · idle 2 min returns it"
              : label}
        </span>
        <div className="flex items-center gap-2">
          {isRunning && !heldByOther ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onOpenFullscreen}
              className="text-[13px] text-paper"
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
    </div>
  );
}
