export function composerCanSend(draft: string, fileCount: number): boolean {
  return draft.trim().length > 0 || fileCount > 0;
}

export function composerShouldSend(event: {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey?: boolean;
  isComposing?: boolean;
}): boolean {
  if (event.isComposing || event.altKey) return false;
  if (event.ctrlKey || event.metaKey) return false;
  return event.key === "Enter" && !event.shiftKey;
}

const MESSAGE_PREFIX = "Message ";
const PLACEHOLDER_MAX_CHARS = 22;

export function composerPlaceholder(name: string, maxChars = PLACEHOLDER_MAX_CHARS): string {
  const full = `${MESSAGE_PREFIX}${name}`;
  if (full.length <= maxChars) return full;
  const room = maxChars - MESSAGE_PREFIX.length - 1;
  if (room < 1) return "Message…";
  return `${MESSAGE_PREFIX}${name.slice(0, room)}…`;
}
