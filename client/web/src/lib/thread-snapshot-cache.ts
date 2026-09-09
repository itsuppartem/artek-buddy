import type { ThreadMessagePage, ThreadSnapshot } from "../types";
import { mergeThreadSnapshot, prependThreadMessagePage } from "./thread-events";

export const THREAD_SNAPSHOT_CACHE_LIMIT = 3;

export type ThreadCacheEntry = {
  snapshot: ThreadSnapshot;
  preserveLoadedHistory: boolean;
  atStart: boolean;
};

export function createThreadSnapshotCache(): Map<string, ThreadCacheEntry> {
  return new Map();
}

export function peekThread(
  cache: Map<string, ThreadCacheEntry>,
  botId: string,
): ThreadCacheEntry | undefined {
  return cache.get(botId);
}

export function touchThread(
  cache: Map<string, ThreadCacheEntry>,
  botId: string,
): ThreadCacheEntry | undefined {
  const entry = cache.get(botId);
  if (!entry) return undefined;
  cache.delete(botId);
  cache.set(botId, entry);
  return entry;
}

export function rememberThread(
  cache: Map<string, ThreadCacheEntry>,
  botId: string,
  entry: ThreadCacheEntry,
  limit = THREAD_SNAPSHOT_CACHE_LIMIT,
): ThreadCacheEntry {
  cache.delete(botId);
  cache.set(botId, entry);
  while (cache.size > limit) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined || oldest === botId) break;
    cache.delete(oldest);
  }
  return entry;
}

export function forgetThread(cache: Map<string, ThreadCacheEntry>, botId: string): void {
  cache.delete(botId);
}

export function applySnapshotForBot(
  cache: Map<string, ThreadCacheEntry>,
  botId: string,
  incoming: ThreadSnapshot,
  limit = THREAD_SNAPSHOT_CACHE_LIMIT,
): ThreadCacheEntry | undefined {
  if (incoming.botId !== botId) return cache.get(botId);
  const prev = cache.get(botId);
  const merged = mergeThreadSnapshot(
    prev?.snapshot ?? null,
    incoming,
    prev?.preserveLoadedHistory ?? false,
  );
  const snapshot =
    prev?.preserveLoadedHistory && prev.snapshot
      ? { ...merged, olderCursor: prev.snapshot.olderCursor }
      : merged;
  return rememberThread(
    cache,
    botId,
    {
      snapshot,
      preserveLoadedHistory: prev?.preserveLoadedHistory ?? false,
      atStart: snapshot.olderCursor == null || (prev?.atStart ?? false),
    },
    limit,
  );
}

export function applyOlderPageForBot(
  cache: Map<string, ThreadCacheEntry>,
  botId: string,
  page: ThreadMessagePage,
  limit = THREAD_SNAPSHOT_CACHE_LIMIT,
): ThreadCacheEntry | undefined {
  const prev = cache.get(botId);
  if (!prev) return undefined;
  if (page.threadId && prev.snapshot.threadId && page.threadId !== prev.snapshot.threadId) {
    return prev;
  }
  const snapshot = prependThreadMessagePage(prev.snapshot, page);
  if (!snapshot) return prev;
  return rememberThread(
    cache,
    botId,
    {
      snapshot,
      preserveLoadedHistory: true,
      atStart: page.olderCursor == null ? true : prev.atStart,
    },
    limit,
  );
}
