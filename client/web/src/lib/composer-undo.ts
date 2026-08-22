export type ComposerHistory = {
  entries: string[];
  index: number;
};

export type ComposerKey = {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey?: boolean;
  isComposing?: boolean;
};

const COALESCE_MS = 400;
const MAX_ENTRIES = 200;

export function createComposerHistory(value = ""): ComposerHistory {
  return { entries: [value], index: 0 };
}

export function resetComposerHistory(value = ""): ComposerHistory {
  return createComposerHistory(value);
}

function isTypingBurst(prev: string, next: string): boolean {
  return Math.abs(prev.length - next.length) === 1;
}

export function pushComposerChange(
  history: ComposerHistory,
  value: string,
  now: number,
  lastAt: number,
  coalesceMs = COALESCE_MS,
): ComposerHistory {
  const current = history.entries[history.index] ?? "";
  if (current === value) return history;
  const base = history.entries.slice(0, history.index + 1);
  const coalesce = lastAt > 0 && now - lastAt < coalesceMs && isTypingBurst(current, value);
  if (coalesce && base.length) {
    base[base.length - 1] = value;
    return { entries: base, index: base.length - 1 };
  }
  base.push(value);
  if (base.length > MAX_ENTRIES) {
    base.splice(0, base.length - MAX_ENTRIES);
  }
  return { entries: base, index: base.length - 1 };
}

export function composerUndo(
  history: ComposerHistory,
): { history: ComposerHistory; value: string } | null {
  if (history.index <= 0) return null;
  const index = history.index - 1;
  return { history: { entries: history.entries, index }, value: history.entries[index] ?? "" };
}

export function composerRedo(
  history: ComposerHistory,
): { history: ComposerHistory; value: string } | null {
  if (history.index >= history.entries.length - 1) return null;
  const index = history.index + 1;
  return { history: { entries: history.entries, index }, value: history.entries[index] ?? "" };
}

export function composerUndoKind(event: ComposerKey): "undo" | "redo" | null {
  if (event.isComposing || event.altKey) return null;
  const key = event.key.toLowerCase();
  const mod = event.ctrlKey || event.metaKey;
  if (!mod || (key !== "z" && key !== "y")) return null;
  if (key === "y" && event.ctrlKey && !event.metaKey) return "redo";
  if (key === "z" && event.shiftKey) return "redo";
  if (key === "z") return "undo";
  return null;
}
