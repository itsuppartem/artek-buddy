export type PluginChip = { slug: string; name: string };

export function hidePluginSlug(
  hidden: Record<string, string[]>,
  botId: string,
  slug: string,
): Record<string, string[]> {
  const already = hidden[botId] ?? [];
  if (already.includes(slug)) return hidden;
  return { ...hidden, [botId]: [...already, slug] };
}

export function visiblePluginApps(
  apps: PluginChip[],
  hidden: Record<string, string[]>,
  botId: string | undefined,
): PluginChip[] {
  if (!botId) return apps;
  const skipped = new Set(hidden[botId] ?? []);
  return apps.filter((app) => !skipped.has(app.slug));
}

export function pluginAskDraft(name: string): string {
  return `please use ${name}`;
}

export function pluginChipClickShouldFill(hadPointerDown: boolean): boolean {
  return hadPointerDown;
}
