import type { MouseEvent } from "react";
import { api } from "../../api";
import { ChatMarkdown } from "../../lib/chat-markdown";
import { stripMarkdown } from "../../lib/markdown";
import { isHiddenLiveDraft } from "../../lib/thread-events";
import type { ThreadMessage } from "../../types";
import { Button } from "../../ui/button";
import { AskCard } from "./AskCard";
import { FileCard } from "./FileCard";

export function replyExcerpt(message: ThreadMessage): string {
  if (message.replyTo?.excerpt) return message.replyTo.excerpt;
  const text = message.blocks.find((block) => "text" in block && block.text);
  return text && "text" in text ? text.text : "Message";
}

export function MessageView({
  botId,
  canAnswer,
  message,
  queued = false,
  offlineCaption,
  runStatus,
  onAnswer,
  onOpenBot,
  onOpenComputer,
  onSubagentChange,
  onContextMenu,
}: {
  botId: string;
  canAnswer: boolean;
  message: ThreadMessage;
  queued?: boolean;
  offlineCaption?: string;
  runStatus?: string;
  onAnswer: (text: string) => Promise<void>;
  onOpenBot: (botId: string) => void;
  onOpenComputer?: () => void;
  onSubagentChange?: () => void;
  onContextMenu?: (event: MouseEvent, message: ThreadMessage) => void;
}) {
  const quote = message.replyTo;
  return (
    <div
      data-testid="thread-message"
      data-role={message.role}
      data-message-id={message.id}
      data-queued={queued ? "true" : undefined}
      className="min-w-0"
      onContextMenu={(event) => {
        if (!onContextMenu) return;
        event.preventDefault();
        onContextMenu(event, message);
      }}
    >
      {quote ? (
        <div className={`mb-1 flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
          <div className="max-w-[70%] min-w-0 break-words [overflow-wrap:anywhere] border-l-2 border-tan pl-2.5 text-[13px] leading-[1.4] text-mute">
            {stripMarkdown(quote.excerpt)}
          </div>
        </div>
      ) : null}
      {message.blocks.map((block, index) => {
        if (block.kind === "meta") {
          return (
            <div
              key={index}
              data-testid="meta-block"
              className="flex items-center justify-center gap-2 py-1 text-[13.5px] text-mute"
            >
              <span className="text-tan">◷</span>
              <span>{block.text}</span>
            </div>
          );
        }
        if (block.kind === "progress") {
          if (isHiddenLiveDraft(message)) {
            return null;
          }
          return (
            <div key={index} className="flex justify-start" data-testid="progress-block">
              <div className="max-w-[74%] min-w-0 break-words [overflow-wrap:anywhere] rounded-[16px] bg-plate px-[18px] py-3 text-[15.5px] leading-[1.5] text-paper">
                <ChatMarkdown streaming>{block.text}</ChatMarkdown>
              </div>
            </div>
          );
        }
        if (block.kind === "subagent") {
          const running = block.status === "queued" || block.status === "running";
          const failed = block.status === "failed" || block.status === "cancelled";
          const label = block.index ? `#${block.index} ${block.name}` : block.name;
          return (
            <div
              key={index}
              data-testid="subagent-card"
              data-status={block.status}
              className="max-w-[74%] min-w-[340px] w-fit rounded-[18px] border border-[#232326] bg-[#17171A] px-[18px] py-4"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[15px] font-medium text-[#ECECEE]">{label}</span>
                <span
                  className="rounded-full px-[11px] py-1 text-[13px]"
                  style={{
                    background: failed
                      ? "rgba(230,87,7,.14)"
                      : running
                        ? "rgba(245,160,60,.14)"
                        : "rgba(48,162,75,.14)",
                    color: failed ? "#E65707" : running ? "#D4A017" : "#4ECB71",
                    animation: running ? "abPulse 1.2s ease-in-out infinite" : undefined,
                  }}
                >
                  {block.status}
                </span>
              </div>
              <div className="mt-2 text-[13.5px] text-[#85858A]">{block.task}</div>
              {block.clarifications ? (
                <div className="mt-2 text-[13px] leading-[1.45] text-[#9A9AA0]">
                  {block.clarifications}
                </div>
              ) : null}
              {block.progress || block.result ? (
                <div className="mt-2.5 text-[14.5px] leading-[1.5] text-[#A8A8AD]">
                  <ChatMarkdown streaming={running}>
                    {block.result || block.progress || ""}
                  </ChatMarkdown>
                </div>
              ) : null}
              {botId && block.agentId ? (
                <div className="mt-3 flex gap-2">
                  {running ? (
                    <button
                      type="button"
                      className="rounded-full bg-[#2A1510] px-3 py-1 text-[13px] text-[#E65707] hover:bg-[#3A1C14]"
                      onClick={() => {
                        void api.subagents
                          .stop(botId, block.agentId)
                          .then(() => onSubagentChange?.())
                          .catch(() => undefined);
                      }}
                    >
                      Stop
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="rounded-full bg-[#1B1B1E] px-3 py-1 text-[13px] text-[#C9C9CE] hover:bg-[#242428]"
                      onClick={() => {
                        void api.subagents
                          .restart(botId, block.agentId)
                          .then(() => onSubagentChange?.())
                          .catch(() => undefined);
                      }}
                    >
                      Restart
                    </button>
                  )}
                </div>
              ) : null}
            </div>
          );
        }
        if (block.kind === "child_bot") {
          const removed = block.status === "deleted" || block.status === "archived";
          return (
            <button
              key={index}
              type="button"
              data-testid="child-bot-card"
              data-status={block.status}
              disabled={removed}
              onClick={() => onOpenBot(block.botId)}
              className="w-[min(340px,90%)] rounded-[18px] border border-[#232326] bg-[#17171A] px-[18px] py-4 text-left disabled:opacity-60"
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-medium text-[#ECECEE]">{block.name}</span>
                <span className="rounded-full bg-[rgba(48,162,75,.14)] px-[11px] py-1 text-[13px] text-[#4ECB71]">
                  {block.status}
                </span>
              </div>
              {block.title ? (
                <div className="mt-2 text-[14.5px] leading-[1.5] text-[#A8A8AD]">{block.title}</div>
              ) : null}
            </button>
          );
        }
        if (block.kind === "text" && message.role === "user") {
          return (
            <div key={index} className="flex flex-col items-end gap-1">
              <div className="max-w-[70%] min-w-0 break-words [overflow-wrap:anywhere] rounded-[16px] bg-paper px-[18px] py-3 text-[15.5px] leading-[1.45] text-ink">
                {block.text}
              </div>
              {offlineCaption ? (
                <div
                  data-testid="offline-sent-caption"
                  className="max-w-[70%] text-[12.5px] text-mute"
                >
                  {offlineCaption}
                </div>
              ) : null}
            </div>
          );
        }
        if (block.kind === "text") {
          return (
            <div key={index} className="flex justify-start">
              <div className="max-w-[74%] min-w-0 break-words [overflow-wrap:anywhere] rounded-[16px] bg-plate px-[18px] py-3 text-[15.5px] leading-[1.5] text-paper">
                <ChatMarkdown>{block.text}</ChatMarkdown>
              </div>
            </div>
          );
        }
        if (block.kind === "card") {
          return (
            <div key={index} className="flex justify-start" data-testid="check-card">
              <div className="flex flex-col gap-2 rounded-[20px] bg-[#1A1A1D] px-5 py-4">
                {block.lines.map((line) => (
                  <div key={line.k} className="flex items-baseline gap-2.5 text-[15px]">
                    <span className="text-[#30A24B]">✓</span>
                    <span className="font-semibold text-white">{line.k}</span>
                    <span className="text-[#85858A]">→</span>
                    <span>{line.v}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        }
        if (block.kind === "file") {
          return (
            <div
              key={index}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <FileCard block={block} />
            </div>
          );
        }
        if (block.kind === "ask") {
          return <AskCard key={index} block={block} canAnswer={canAnswer} onAnswer={onAnswer} />;
        }
        if (block.kind === "plugin") {
          return (
            <div
              key={index}
              data-testid="plugin-card"
              className="max-w-[74%] rounded-[10px] border border-hairline border-l-[3px] border-l-tan bg-plate px-3.5 py-3"
            >
              <div className="text-[13px] font-medium text-tan">{block.name}</div>
              <div className="mt-1.5 text-[14.5px] leading-[1.5] text-paper">
                <ChatMarkdown>{block.text}</ChatMarkdown>
              </div>
            </div>
          );
        }
        if (block.kind === "computer") {
          const waiting =
            (block.state === "waiting" || block.state === "waiting_takeover") &&
            runStatus === "waiting_takeover";
          return (
            <div
              key={index}
              data-testid="computer-card"
              className="w-[340px] rounded-[18px] border border-[#232326] bg-[#17171A] px-[18px] py-4"
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-medium text-[#ECECEE]">Computer</span>
                <span className="rounded-full bg-[rgba(48,162,75,.14)] px-[11px] py-1 text-[13px] text-[#4ECB71]">
                  {waiting ? "waiting" : "done"}
                </span>
              </div>
              <div className="my-2.5 text-[14.5px] leading-[1.5] text-[#A8A8AD]">
                <ChatMarkdown>{block.text}</ChatMarkdown>
              </div>
              {waiting ? (
                <Button
                  type="button"
                  data-testid="open-computer"
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenComputer?.()}
                >
                  Open computer
                </Button>
              ) : null}
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}
