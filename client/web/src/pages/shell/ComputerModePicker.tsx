import {
  type MouseEvent,
  type RefObject,
  type SyntheticEvent,
  useEffect,
  useState,
} from "react";
import { api } from "../../api";
import { completeOwnerConsent, fulfillOwnerJob, isAutoOwnerJob, reportOwnerJobError } from "../../lib/consent";
import { previewKind } from "../../lib/uploads";
import { isCronShape } from "../../lib/cron";
import {
  computerLabel,
  computerModeHint,
  computerPaneState,
  embeddableScreenUrl,
  overlayPointerEvents,
  previewPointerEvents,
  screenIframeSandbox,
  screenTargetKey,
} from "../../lib/screen";
import { ChatMarkdown } from "../../lib/chat-markdown";
import { artifactUrl, DownloadCancelled, downloadArtifact, formatBytes } from "../../lib/files";
import { stripMarkdown } from "../../lib/markdown";
import {
  isComputerStatusEvent,
  reduceComputerStatus,
  reduceThreadSnapshot,
} from "../../lib/thread-events";
import type {
  Bot,
  ComputerMode,
  ComputerStatus,
  ProductEvent,
  MemoryDocument,
  Routine,
  ThreadMessage,
  ThreadSnapshot,
} from "../../types";
import { BotAvatar } from "../../ui/bot-avatar";
import { Button } from "../../ui/button";

export function ComputerModePicker({
  value,
  onChange,
}: {
  value: ComputerMode;
  onChange: (value: ComputerMode) => void;
}) {
  return (
    <div className="mt-4">
      <div className="text-[14px] text-[#85858A]">Computer</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {(["team", "dedicated"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            data-testid={mode === "team" ? "computer-mode-team" : "computer-mode-private"}
            aria-pressed={value === mode}
            onClick={() => onChange(mode)}
            className={`rounded-[11px] border px-3.5 py-3 text-[14px] capitalize ${
              value === mode
                ? "border-[#6C6C70] bg-[#1A1A1D] text-[#ECECEE]"
                : "border-[#26262A] text-[#85858A]"
            }`}
          >
            {mode === "team" ? "Team" : "Private"}
          </button>
        ))}
      </div>
      <p data-testid="computer-mode-hint" className="mt-2 text-[12.5px] leading-5 text-[#6C6C70]">
        {computerModeHint(value)}
      </p>
    </div>
  );
}
