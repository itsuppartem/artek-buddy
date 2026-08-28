export type InboxEmptyState = "create" | "archived" | null;
export type SidebarView = "inbox" | "archived";

export function inboxEmptyState(inboxCount: number, archivedCount: number): InboxEmptyState {
  if (inboxCount > 0) return null;
  return archivedCount > 0 ? "archived" : "create";
}

export function inboxSearchEmpty(query: string, matchCount: number): boolean {
  return query.trim().length > 0 && matchCount === 0;
}

export function sortInboxBots<T extends { id: string; pinned: boolean; createdAt: string }>(
  bots: T[],
): T[] {
  return [...bots].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    const created = a.createdAt.localeCompare(b.createdAt);
    if (created) return created;
    return a.id.localeCompare(b.id);
  });
}

export function filterBots<
  T extends { name: string; preview?: string | null; title?: string | null },
>(bots: T[], query: string, previewOf: (bot: T) => string): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return bots;
  return bots.filter((bot) => `${bot.name} ${previewOf(bot)}`.toLowerCase().includes(needle));
}

export type HighlightPart = { text: string; hit: boolean };

export function splitQueryMatch(text: string, query: string): HighlightPart[] {
  const needle = query.trim();
  if (!needle) return [{ text, hit: false }];
  const index = text.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) return [{ text, hit: false }];
  const parts: HighlightPart[] = [];
  if (index > 0) parts.push({ text: text.slice(0, index), hit: false });
  parts.push({ text: text.slice(index, index + needle.length), hit: true });
  const rest = text.slice(index + needle.length);
  if (rest) parts.push({ text: rest, hit: false });
  return parts;
}

export function inboxFallbackPath(
  botId: string | undefined,
  listedIds: string[],
  firstInboxId: string | undefined,
  requestedId: string | null,
): string | null {
  if (botId && listedIds.includes(botId)) return null;
  if (requestedId && botId === requestedId) return null;
  if (!botId && firstInboxId) return `/app/${firstInboxId}`;
  if (botId && !listedIds.includes(botId)) {
    return firstInboxId ? `/app/${firstInboxId}` : "/app";
  }
  return null;
}

export function inboxRowClickShouldOpen(hadPointerDown: boolean): boolean {
  return hadPointerDown;
}
