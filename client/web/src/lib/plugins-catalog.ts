export type PluginCatalogRow = { slug: string; name: string };

export function filterPluginCatalog<T extends PluginCatalogRow>(items: T[], query: string): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter(
    (item) => item.slug.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
  );
}
