export type InboxEmptyState = "create" | "archived" | null;
export type SidebarView = "inbox" | "archived";

export function inboxEmptyState(inboxCount: number, archivedCount: number): InboxEmptyState {
  if (inboxCount > 0) return null;
  return archivedCount > 0 ? "archived" : "create";
}

export function filterBots<T extends { name: string; preview?: string | null; title?: string | null }>(
  bots: T[],
  query: string,
  previewOf: (bot: T) => string,
): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return bots;
  return bots.filter((bot) => `${bot.name} ${previewOf(bot)}`.toLowerCase().includes(needle));
}
