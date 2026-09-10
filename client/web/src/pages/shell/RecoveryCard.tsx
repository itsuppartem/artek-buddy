import { useState } from "react";
import { ChatMarkdown } from "../../lib/chat-markdown";
import type { ThreadMessage } from "../../types";

type RecoveryBlock = Extract<ThreadMessage["blocks"][number], { kind: "recovery" }>;

export function RecoveryCard({
  block,
  canAnswer,
  onRecover,
}: {
  block: RecoveryBlock;
  canAnswer: boolean;
  onRecover: (action: "continue" | "new_attempt") => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(action: "continue" | "new_attempt") {
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await onRecover(action);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply that recovery");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      data-testid="recovery-card"
      data-path={block.path}
      data-status={block.status ?? "pending"}
      className="min-w-0 max-w-[74%] rounded-[14px] border border-hairline bg-plate px-5 py-[17px] shadow-[0_10px_30px_rgba(29,49,76,0.08)]"
    >
      <div className="mb-2 font-mono text-[9px] tracking-[0.06em] text-copper uppercase">
        Host restarted
      </div>
      <div className="min-w-0 text-[15.5px] leading-[1.5] break-words [overflow-wrap:anywhere] text-paper">
        <ChatMarkdown>{block.text}</ChatMarkdown>
      </div>
      {block.detail ? (
        <pre className="mt-3 max-w-full min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-xl bg-ink px-3.5 py-3 font-mono text-[12.5px] leading-[1.7] text-mute">
          {block.detail}
        </pre>
      ) : null}
      {block.status === "resolved" ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-sage">Resolved</div>
      ) : !canAnswer ? (
        <div className="mt-3.5 text-[13.5px] font-medium text-mute">No longer active</div>
      ) : (
        <div className="mt-3.5 flex flex-col gap-2">
          {(block.actions ?? []).map((act) => (
            <button
              key={act.id}
              type="button"
              data-testid="recovery-option"
              disabled={submitting}
              onClick={() => {
                const action = act.id === "continue" ? "continue" : "new_attempt";
                void submit(action);
              }}
              className="group flex w-full items-center rounded-[12px] border border-hairline bg-plate px-3.5 py-2.5 text-left transition hover:border-hairline hover:bg-raised disabled:opacity-50"
            >
              <span className="min-w-0 break-words [overflow-wrap:anywhere] text-[14px] leading-[1.4] text-paper">
                {act.label}
              </span>
            </button>
          ))}
        </div>
      )}
      {error ? <div className="mt-2 text-[13px] text-danger">{error}</div> : null}
    </div>
  );
}
