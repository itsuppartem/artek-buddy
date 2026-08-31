import { describe, expect, it } from "vitest";
import {
  filterPluginCatalog,
  pluginCatalogScrollAfterUpdate,
  pluginSearchShouldPreventDefault,
} from "./plugins-catalog";

const catalog = [
  { slug: "mail", name: "Mail" },
  { slug: "docs", name: "Docs" },
  { slug: "needssetup", name: "Needs Setup" },
];

describe("filterPluginCatalog", () => {
  it("filters as the owner types, without waiting for Enter", () => {
    expect(filterPluginCatalog(catalog, "doc").map((row) => row.slug)).toEqual(["docs"]);
    expect(filterPluginCatalog(catalog, "")).toEqual(catalog);
  });

  it("keeps Enter in Search apps from submitting or closing the pane", () => {
    expect(pluginSearchShouldPreventDefault("Enter")).toBe(true);
    expect(pluginSearchShouldPreventDefault("a")).toBe(false);
    expect(pluginSearchShouldPreventDefault("Escape")).toBe(false);
  });

  it("keeps catalog scroll where the owner left it after a filter", () => {
    expect(pluginCatalogScrollAfterUpdate(120, 200)).toBe(120);
    expect(pluginCatalogScrollAfterUpdate(120, 40)).toBe(40);
    expect(pluginCatalogScrollAfterUpdate(-8, 40)).toBe(0);
  });
});
