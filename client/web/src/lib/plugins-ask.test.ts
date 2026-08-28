import { describe, expect, it } from "vitest";
import { hidePluginSlug, visiblePluginApps } from "./plugins-ask";

const docs = { slug: "docs", name: "Docs" };
const extra = { slug: "extra", name: "Extra" };

describe("plugin composer chips", () => {
  it("hides a dismissed slug for that chat only", () => {
    const hidden = hidePluginSlug({}, "bot-a", docs.slug);
    expect(visiblePluginApps([docs, extra], hidden, "bot-a")).toEqual([extra]);
    expect(visiblePluginApps([docs, extra], hidden, "bot-b")).toEqual([docs, extra]);
  });
});
