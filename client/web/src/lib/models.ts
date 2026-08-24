export const NEEDS_MODEL_TEXT = "Open Models. Paste an API key, pick a model, then send again.";

export const MODEL_PROVIDERS = [
  { id: "cursor", label: "Cursor" },
  { id: "openrouter", label: "OpenRouter" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "xai", label: "xAI (Grok)" },
] as const;

export type ModelProviderId = (typeof MODEL_PROVIDERS)[number]["id"];

export function defaultModelValue(provider: string, modelId: string): string {
  return `${provider}:${modelId}`;
}

export function parseDefaultModelValue(value: string): { provider: string; model: string } | null {
  const index = value.indexOf(":");
  if (index <= 0 || index === value.length - 1) return null;
  return { provider: value.slice(0, index), model: value.slice(index + 1) };
}

export function maskedKey(lastFour: string | null | undefined): string {
  return lastFour ? `•••• ${lastFour}` : "";
}
