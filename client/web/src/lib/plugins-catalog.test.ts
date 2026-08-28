import { describe, expect, it } from "vitest";
import { filterPluginCatalog } from "./plugins-catalog";

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
});
