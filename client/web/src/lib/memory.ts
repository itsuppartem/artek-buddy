import type { MemoryDocument } from "../types";

const PATH = /^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;

export const MEMORY_CHANGED_EVENT = "artek-memory-changed";

export function isMemoryPath(value: string): boolean {
  const path = value.trim();
  return Boolean(path) && !path.includes("..") && PATH.test(path);
}

export function formatMemoryExport(documents: { path: string; content: string }[]): string {
  return documents
    .map((document) => `# ${document.path}\n\n${document.content}`.trimEnd())
    .join("\n\n");
}

export function memoryShelf(path: string): string {
  return path.match(/^entries\/(owner|work|charter)\//)?.[1] ?? "owner";
}

export function memoryKind(path: string): string | null {
  return path.match(/^entries\/(?:(?:owner|work|charter)\/)?([a-z]+)-/)?.[1] ?? null;
}

/** Owner place/person rows are the identity chapter, not a raw kind chip. */
export function memoryChapter(path: string): string | null {
  const kind = memoryKind(path);
  if (kind === "place" || kind === "person") return "identity";
  return kind;
}

export function memoryTitle(document: MemoryDocument): string {
  const line = document.content.trim().split("\n")[0];
  return line || memoryKind(document.path) || document.path;
}

export function defaultMemoryScope(): "bot" | "user" {
  return "bot";
}

export function memoryDeleteName(): string {
  return "Remove";
}

export function dispatchMemoryChanged(type: string): void {
  if (type !== "memory.revised") return;
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(MEMORY_CHANGED_EVENT));
}
