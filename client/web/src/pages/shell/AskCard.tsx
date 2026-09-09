import { useState } from "react";
import { ChatMarkdown } from "../../lib/chat-markdown";
import { completeOwnerConsent } from "../../lib/consent";
import type { ThreadMessage } from "../../types";

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
        await completeOwnerConsent(consentId, picked);
        return;
      }
      await onAnswer(text);
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Could not send that answer");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      data-testid={consentId ? "consent-card" : "ask-card"}
      data-status={block.status ?? "pending"}
      className="min-w-0 max-w-[74%] rounded-[14px] border border-hairline bg-plate px-5 py-[17px] shadow-[0_10px_30px_rgba(29,49,76,0.08)]"
    >
      {consentId ? (
        <div className="mb-2 font-mono text-[9px] tracking-[0.06em] text-copper uppercase">
          Permission for this task
        </div>
      ) : null}
      <div className="min-w-0 text-[15.5px] leading-[1.5] break-words [overflow-wrap:anywhere] text-paper">
        <ChatMarkdown>{block.text}</ChatMarkdown>
      </div>
      {block.detail ? (
        <pre
          data-testid="ask-detail"
          className="mt-3 max-w-full min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-xl bg-ink px-3.5 py-3 font-mono text-[12.5px] leading-[1.7] text-mute"
        >
          {block.detail}
        </pre>
      ) : null}
      {block.status === "answered" ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-sage">
          {block.answer === "Timed out"
            ? "Timed out"
            : block.answer
              ? `Answered: ${block.answer}`
              : "Answered"}
        </div>
      ) : !canAnswer ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-mute">No longer active</div>
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
            className="rounded-[11px] border border-hairline bg-ink px-3.5 py-2.5 text-[14.5px] text-paper outline-none focus:border-tan"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={!answer.trim() || submitting}
              className="rounded-[11px] bg-paper px-[17px] py-2 text-[14.5px] font-medium text-ink disabled:opacity-50"
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
              className="rounded-[11px] border border-hairline px-[17px] py-2 text-[14.5px] text-paper disabled:opacity-50"
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
                    className="group flex w-full items-center rounded-[12px] border border-hairline bg-plate px-3.5 py-2.5 text-left transition hover:border-hairline hover:bg-raised disabled:opacity-50"
                  >
                    <span className="mr-3 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-raised text-[12px] font-semibold text-mute group-hover:bg-hairline group-hover:text-paper">
                      {letter}
                    </span>
                    <span className="min-w-0 break-words [overflow-wrap:anywhere] text-[14px] leading-[1.4] text-paper group-hover:text-paper">
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
                  className="mt-1 self-start text-[13px] text-mute hover:text-paper disabled:opacity-50"
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
                className="rounded-[11px] bg-paper px-[17px] py-2 text-[14.5px] font-medium text-ink disabled:opacity-50"
              >
                {submitting ? "Sending…" : "Send it"}
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setEditing(true)}
                className="rounded-[11px] border border-hairline px-[17px] py-2 text-[14.5px] text-paper disabled:opacity-50"
              >
                Edit first
              </button>
            </div>
          )}
        </div>
      )}
      {fileError ? <div className="mt-2 text-[13px] text-danger">{fileError}</div> : null}
    </div>
  );
}
