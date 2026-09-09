export type PluginCatalogRow = { slug: string; name: string };

export function filterPluginCatalog<T extends PluginCatalogRow>(items: T[], query: string): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter(
    (item) => item.slug.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
  );
}

export function pluginSearchShouldPreventDefault(key: string): boolean {
  return key === "Enter";
}

export function pluginCatalogScrollAfterUpdate(previous: number, max: number): number {
  if (max < 0) return 0;
  return Math.min(Math.max(0, previous), max);
}
