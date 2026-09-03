import type { MouseEvent, MutableRefObject } from "react";
import { stripMarkdown } from "../../lib/markdown";
import { inboxRowClickShouldOpen, inboxSearchEmpty, type SidebarView } from "../../lib/sidebar";
import type { Bot } from "../../types";
import { BotAvatar } from "../../ui/bot-avatar";
import { InboxHit } from "./InboxHit";

export function InboxList({
  sidebarView,
  query,
  bots,
  archived,
  archivedCount,
  activeId,
  inboxPointerDown,
  onBackInbox,
  onRestore,
  onOpenBot,
  onContextMenu,
  onOpenArchived,
}: {
  sidebarView: SidebarView;
  query: string;
  bots: Bot[];
  archived: Bot[];
  archivedCount: number;
  activeId: string | undefined;
  inboxPointerDown: MutableRefObject<string | null>;
  onBackInbox: () => void;
  onRestore: (bot: Bot) => void;
  onOpenBot: (id: string) => void;
  onContextMenu: (bot: Bot, event: MouseEvent<HTMLButtonElement>) => void;
  onOpenArchived: () => void;
}) {
  if (sidebarView === "archived") {
    return (
      <>
        <button
          type="button"
          data-testid="back-inbox"
          onClick={onBackInbox}
          className="mb-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13.5px] text-mute hover:bg-raised hover:text-paper"
        >
          ← Inbox
        </button>
        <div data-testid="archived-list" className="flex flex-col gap-0.5">
          {archived.map((bot) => (
            <div
              key={bot.id}
              data-testid="archived-bot-row"
              data-bot-id={bot.id}
              className="flex items-center gap-3 rounded-xl px-2.5 py-[11px]"
            >
              <BotAvatar color={bot.color} size={38} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-display text-[14.5px] text-paper">
                  <InboxHit text={bot.name} query={query} />
                </div>
                <div className="mt-0.5 truncate text-[12.5px] text-mute">
                  <InboxHit text={stripMarkdown(bot.preview || bot.title)} query={query} />
                </div>
              </div>
              <button
                type="button"
                data-testid="restore-chat"
                onClick={() => onRestore(bot)}
                className="shrink-0 rounded-lg border border-hairline px-2.5 py-1 text-[12.5px] text-paper hover:bg-raised"
              >
                Restore
              </button>
            </div>
          ))}
          {inboxSearchEmpty(query, archived.length) ? (
            <p
              data-testid="inbox-search-empty"
              className="px-2.5 py-3 text-[13px] leading-5 text-mute"
            >
              No chats match. Clear Search or try another name.
            </p>
          ) : null}
        </div>
      </>
    );
  }

  return (
    <>
      {bots.map((bot) => (
        <button
          key={bot.id}
          type="button"
          data-testid="bot-row"
          data-bot-id={bot.id}
          data-bot-name={bot.name}
          aria-label={bot.unread ? `Open chat ${bot.name} (unread)` : `Open chat ${bot.name}`}
          aria-current={activeId === bot.id ? "page" : undefined}
          onPointerDown={() => {
            inboxPointerDown.current = bot.id;
          }}
          onClick={() => {
            if (!inboxRowClickShouldOpen(inboxPointerDown.current === bot.id)) return;
            inboxPointerDown.current = null;
            onOpenBot(bot.id);
          }}
          onContextMenu={(event) => {
            event.preventDefault();
            onContextMenu(bot, event);
          }}
          className={`flex gap-2.5 border-l-[3px] px-2.5 py-[11px] text-left ${
            activeId === bot.id ? "border-tan bg-plate" : "border-transparent hover:bg-raised"
          }`}
        >
          <BotAvatar color={bot.color} size={38} />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span
                className={`flex items-center gap-1.5 font-display text-[14.5px] text-paper ${
                  bot.unread ? "font-semibold" : "font-normal"
                }`}
              >
                <InboxHit text={bot.name} query={query} />
                {bot.pinned ? (
                  <span title="Pinned" className="text-[11px] text-mute">
                    📌
                  </span>
                ) : null}
              </span>
              <span className="flex shrink-0 items-center gap-1.5 text-[12.5px] text-mute">
                {bot.status === "idle" ? "" : bot.status}
                {bot.unread ? (
                  <span
                    data-testid="unread-dot"
                    role="img"
                    aria-label="Unread"
                    className="inline-block h-2.5 w-2.5 rounded-full bg-tan"
                  />
                ) : null}
              </span>
            </div>
            <div
              data-testid="bot-preview"
              className={`mt-0.5 truncate text-[12.5px] ${
                bot.unread ? "font-medium text-paper" : "text-mute"
              }`}
            >
              <InboxHit text={stripMarkdown(bot.preview || bot.title)} query={query} />
            </div>
          </div>
        </button>
      ))}
      {inboxSearchEmpty(query, bots.length) ? (
        <p data-testid="inbox-search-empty" className="px-2.5 py-3 text-[13px] leading-5 text-mute">
          No chats match. Clear Search or try another name.
        </p>
      ) : null}
      {archivedCount > 0 ? (
        <button
          type="button"
          data-testid="open-archived"
          onClick={onOpenArchived}
          className="mt-1 flex items-center justify-between rounded-xl px-2.5 py-[11px] text-left text-[14px] text-mute hover:bg-raised hover:text-paper"
        >
          <span>Archived</span>
          <span data-testid="archived-count">{archivedCount}</span>
        </button>
      ) : null}
    </>
  );
}
