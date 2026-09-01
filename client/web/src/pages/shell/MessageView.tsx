import type { MouseEvent } from "react";
import { ChatMarkdown } from "../../lib/chat-markdown";
import { stripMarkdown } from "../../lib/markdown";
import {
  rememberedFact,
  rememberedLineKind,
  rememberedLinePreview,
} from "../../lib/remembered-line";
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
  canAnswer,
  message,
  queued = false,
  offlineCaption,
  runStatus,
  onAnswer,
  onOpenBot,
  onOpenMemory,
  onOpenComputer,
  onContextMenu,
}: {
  canAnswer: boolean;
  message: ThreadMessage;
  queued?: boolean;
  offlineCaption?: string;
  runStatus?: string;
  onAnswer: (text: string, message: ThreadMessage) => Promise<void>;
  onOpenBot: (botId: string) => void;
  onOpenMemory?: (fact: string) => void;
  onOpenComputer?: () => void;
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
          const kind = rememberedLineKind(block.text);
          const fact = rememberedFact(block.text);
          if (kind && fact && onOpenMemory) {
            return (
              <div key={index} className="flex justify-center py-1">
                <button
                  type="button"
                  data-testid="meta-block"
                  data-memory-line={kind}
                  aria-label="Open in Memory"
                  title={block.text}
                  onClick={() => onOpenMemory(fact)}
                  className="flex max-w-[min(100%,36rem)] min-w-0 items-center gap-2 text-left text-[13.5px] text-mute hover:text-paper"
                >
                  <span className="shrink-0 text-tan">◷</span>
                  <span className="min-w-0 truncate">{rememberedLinePreview(block.text)}</span>
                </button>
              </div>
            );
          }
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
          return null;
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
              className="w-[min(340px,90%)] rounded-[18px] border border-hairline bg-plate px-[18px] py-4 text-left disabled:opacity-60"
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-medium text-paper">{block.name}</span>
                <span className="rounded-full bg-sage-bg px-[11px] py-1 text-[13px] text-sage">
                  {block.status}
                </span>
              </div>
              {block.title ? (
                <div className="mt-2 text-[14.5px] leading-[1.5] text-mute">{block.title}</div>
              ) : null}
            </button>
          );
        }
        if (block.kind === "text" && message.role === "user") {
          return (
            <div key={index} className="flex flex-col items-end gap-1">
              <div
                data-testid="user-text"
                className="max-w-[70%] min-w-0 break-words whitespace-pre-wrap [overflow-wrap:anywhere] rounded-[16px] bg-paper px-[18px] py-3 text-[15.5px] leading-[1.45] text-ink"
              >
                {block.text}
              </div>
              {queued ? (
                <div data-testid="queued-pending" className="max-w-[70%] text-[12.5px] text-mute">
                  Waiting for the host
                </div>
              ) : offlineCaption ? (
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
              <div className="flex flex-col gap-2 rounded-[20px] bg-plate px-5 py-4">
                {block.lines.map((line) => (
                  <div key={line.k} className="flex items-baseline gap-2.5 text-[15px]">
                    <span className="text-sage">✓</span>
                    <span className="font-semibold text-white">{line.k}</span>
                    <span className="text-mute">→</span>
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
          return (
            <AskCard
              key={index}
              block={block}
              canAnswer={canAnswer}
              onAnswer={(text) => onAnswer(text, message)}
            />
          );
        }
        if (block.kind === "plugin") {
          const raw = "url" in block && block.url ? String(block.url) : "";
          let connectHref = "";
          try {
            const parsed = new URL(raw);
            if (parsed.protocol === "https:" || parsed.protocol === "http:") {
              connectHref = parsed.href;
            }
          } catch {
            connectHref = "";
          }
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
              {connectHref ? (
                <a
                  href={connectHref}
                  target="_blank"
                  rel="noreferrer noopener"
                  data-testid="plugin-connect-open"
                  className="mt-2 inline-flex h-8 items-center justify-center gap-2 whitespace-nowrap rounded-[10px] bg-tan px-3 text-[13px] font-medium text-ink no-underline hover:bg-tan-press"
                >
                  Open to connect
                </a>
              ) : null}
            </div>
          );
        }
        if (block.kind === "book") {
          return null;
        }
        if (block.kind === "computer") {
          const waiting =
            (block.state === "waiting" || block.state === "waiting_takeover") &&
            runStatus === "waiting_takeover";
          return (
            <div
              key={index}
              data-testid="computer-card"
              className="w-[340px] rounded-[18px] border border-hairline bg-plate px-[18px] py-4"
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-medium text-paper">Computer</span>
                <span className="rounded-full bg-sage-bg px-[11px] py-1 text-[13px] text-sage">
                  {waiting ? "waiting" : "done"}
                </span>
              </div>
              <div className="my-2.5 text-[14.5px] leading-[1.5] text-mute">
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
