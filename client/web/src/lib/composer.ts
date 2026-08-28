export function composerCanSend(draft: string, fileCount: number): boolean {
  return draft.trim().length > 0 || fileCount > 0;
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
