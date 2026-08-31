import { describe, expect, it } from "vitest";
import {
  hidePluginSlug,
  pluginAskDraft,
  pluginChipClickShouldFill,
  visiblePluginApps,
} from "./plugins-ask";

const docs = { slug: "docs", name: "Docs" };
const extra = { slug: "extra", name: "Extra" };

describe("plugin composer chips", () => {
  it("hides a dismissed slug for that chat only", () => {
    const hidden = hidePluginSlug({}, "bot-a", docs.slug);
    expect(visiblePluginApps([docs, extra], hidden, "bot-a")).toEqual([extra]);
    expect(visiblePluginApps([docs, extra], hidden, "bot-b")).toEqual([docs, extra]);
  });

  it("fills please use {name} and does not look like a send", () => {
    expect(pluginAskDraft("Hacker News")).toBe("please use Hacker News");
    expect(pluginAskDraft("Docs")).toBe("please use Docs");
  });

  it("ignores a click that never pressed the chip (Connect leftover)", () => {
    expect(pluginChipClickShouldFill(false)).toBe(false);
    expect(pluginChipClickShouldFill(true)).toBe(true);
  });
});
