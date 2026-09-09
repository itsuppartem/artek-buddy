export const REMEMBERED_LINE_MAX = 72;

export function rememberedLineKind(text: string): "remembered" | "forgot" | null {
  const line = (text || "").trim();
  if (/^Remembered:/i.test(line)) return "remembered";
  if (/^Forgot:/i.test(line)) return "forgot";
  return null;
}

export function rememberedFact(text: string): string {
  const line = (text || "").trim();
  return line.replace(/^(Remembered|Forgot):\s*/i, "").trim();
}

export function rememberedLinePreview(text: string, max = REMEMBERED_LINE_MAX): string {
  const clean = (text || "").replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}

export function memoryDocMatchesRemembered(content: string, fact: string): boolean {
  const hay = (content || "").replace(/\s+/g, " ").trim().toLowerCase();
  const needle = (fact || "").replace(/…$/u, "").replace(/\s+/g, " ").trim().toLowerCase();
  if (!hay || !needle) return false;
  return (
    hay.includes(needle) || needle.startsWith(hay.slice(0, Math.min(hay.length, needle.length)))
  );
}
