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

type AskBlock = Extract<ThreadMessage["blocks"][number], { kind: "ask" }>;


export function AskCard({
  block,
  canAnswer,
  onAnswer,
}: {
  block: AskBlock;
  canAnswer: boolean;
  onAnswer: (text: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [fileError, setFileError] = useState("");
  const consentId = block.consentId || "";

  async function submitAnswer(value: string, decision?: string) {
    const text = value.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    setFileError("");
    try {
      if (consentId) {
        const picked = decision || text;
        try {
          await completeOwnerConsent(consentId, picked);
        } catch (err) {
          setFileError(err instanceof Error ? err.message : "Could not run that on this computer");
        }
        return;
      }
      await onAnswer(text);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      data-testid={consentId ? "consent-card" : "ask-card"}
      data-status={block.status ?? "pending"}
      className="min-w-0 max-w-[74%] rounded-[20px] border border-[#242428] bg-[#141417] px-5 py-[17px]"
    >
      <div className="min-w-0 text-[15.5px] leading-[1.5] break-words [overflow-wrap:anywhere] text-[#ECECEE]">
        <ChatMarkdown>{block.text}</ChatMarkdown>
      </div>
      {block.detail ? (
        <pre
          data-testid="ask-detail"
          className="mt-3 max-w-full min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-xl bg-[#0E0E10] px-3.5 py-3 font-mono text-[12.5px] leading-[1.7] text-[#85858A]"
        >
          {block.detail}
        </pre>
      ) : null}
      {block.status === "answered" ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-[#4ECB71]">
          {block.answer ? `Answered: ${block.answer}` : "Answered"}
        </div>
      ) : !canAnswer ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-[#85858A]">No longer active</div>
      ) : editing ? (
        <form
          className="mt-3.5 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submitAnswer(answer);
          }}
        >
          <input
            aria-label="Answer"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Type your answer"
            className="rounded-[11px] border border-[#303035] bg-[#0E0E10] px-3.5 py-2.5 text-[14.5px] text-[#ECECEE] outline-none focus:border-[#66666D]"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={!answer.trim() || submitting}
              className="rounded-[11px] bg-[#F1F1EF] px-[17px] py-2 text-[14.5px] font-medium text-[#17171A] disabled:opacity-50"
            >
              {submitting ? "Sending…" : "Send answer"}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => {
                setAnswer("");
                setEditing(false);
              }}
              className="rounded-[11px] border border-[#26262A] px-[17px] py-2 text-[14.5px] text-[#C9C9CE] disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="mt-3.5">
          {block.actions && block.actions.length > 0 ? (
            <div className="flex flex-col gap-2">
              {block.actions.map((act, i) => {
                const letter = String.fromCharCode(65 + (i % 26));
                return (
                  <button
                    key={act.id}
                    type="button"
                    data-testid="ask-option"
                    disabled={submitting}
                    onClick={() => void submitAnswer(act.label, act.id)}
                    className="group flex w-full items-center rounded-[12px] border border-[#242429] bg-[#17171B] px-3.5 py-2.5 text-left transition hover:border-[#383842] hover:bg-[#1E1E23] disabled:opacity-50"
                  >
                    <span className="mr-3 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#232328] text-[12px] font-semibold text-[#8E8E94] group-hover:bg-[#2A2A30] group-hover:text-[#DFDFE2]">
                      {letter}
                    </span>
                    <span className="min-w-0 break-words [overflow-wrap:anywhere] text-[14px] leading-[1.4] text-[#DFDFE2] group-hover:text-white">
                      {act.label}
                    </span>
                  </button>
                );
              })}
              {consentId ? null : (
              <button
                type="button"
                disabled={submitting}
                onClick={() => setEditing(true)}
                className="mt-1 self-start text-[13px] text-[#85858A] hover:text-[#C9C9CE] disabled:opacity-50"
              >
                Type custom reply…
              </button>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={submitting}
                onClick={() => void submitAnswer("approved")}
                className="rounded-[11px] bg-[#F1F1EF] px-[17px] py-2 text-[14.5px] font-medium text-[#17171A] disabled:opacity-50"
              >
                {submitting ? "Sending…" : "Send it"}
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setEditing(true)}
                className="rounded-[11px] border border-[#26262A] px-[17px] py-2 text-[14.5px] text-[#C9C9CE] disabled:opacity-50"
              >
                Edit first
              </button>
            </div>
          )}
        </div>
      )}
      {fileError ? (
        <div className="mt-2 text-[13px] text-[#E25D5D]">{fileError}</div>
      ) : null}
    </div>
  );
}
