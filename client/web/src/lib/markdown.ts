export type ChatMarkdownProps = {
  children: string;
  streaming?: boolean;
};

const protocolPattern = /^([a-z][a-z\d+.-]*):/i;
const safeProtocols = new Set(["http", "https", "mailto", "tel"]);

export function sanitizeMarkdownUrl(url: string, allowRelative = false): string | undefined {
  const value = url.trim();
  const protocol = value.match(protocolPattern)?.[1]?.toLowerCase();
  if (protocol) return safeProtocols.has(protocol) ? value : undefined;
  if (
    allowRelative &&
    (value.startsWith("/") ||
      value.startsWith("./") ||
      value.startsWith("../") ||
      value.startsWith("#"))
  ) {
    return value;
  }
  return undefined;
}

export function closeUnterminatedFence(markdown: string): string {
  let openFence: { marker: "`" | "~"; length: number } | undefined;
  for (const line of markdown.split("\n")) {
    const match = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (!match?.[1]) continue;
    const marker = match[1][0] as "`" | "~";
    if (!openFence) {
      openFence = { marker, length: match[1].length };
      continue;
    }
    if (
      marker === openFence.marker &&
      match[1].length >= openFence.length &&
      (match[2] ?? "").trim() === ""
    ) {
      openFence = undefined;
    }
  }
  return openFence ? `${markdown}\n${openFence.marker.repeat(openFence.length)}` : markdown;
}

export function stripMarkdown(text: string): string {
  if (!text) return "";
  return (
    text
      // Remove fenced code blocks
      .replace(/```[\s\S]*?```/g, "")
      // Remove inline code
      .replace(/`([^`]+)`/g, "$1")
      // Remove images ![alt](url) -> alt
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
      // Remove links [text](url) -> text
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      // Remove bold / italic / bold-italic (asterisks and underscores)
      .replace(/(\*{1,3}|_{1,3})([^*_]+?)\1/g, "$2")
      // Remove strikethrough ~~text~~
      .replace(/~~([^~]+)~~/g, "$1")
      // Remove header markers #
      .replace(/^#{1,6}\s+/gm, "")
      // Remove blockquotes >
      .replace(/^>\s*/gm, "")
      // Remove list markers (*, -, +, 1.)
      .replace(/^(\s*[-*+]|\s*\d+\.)\s+/gm, "")
      // Remove html tags
      .replace(/<[^>]+>/g, "")
      // Collapse whitespace
      .replace(/\s+/g, " ")
      .trim()
  );
}
