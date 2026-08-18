import { describe, expect, it } from "vitest";
import { filterBots, inboxEmptyState } from "./sidebar";

describe("inboxEmptyState", () => {
  it("shows create when there are no chats at all", () => {
    expect(inboxEmptyState(0, 0)).toBe("create");
  });

  it("points at archived when the inbox is empty but chats were put away", () => {
    expect(inboxEmptyState(0, 2)).toBe("archived");
  });

  it("stays quiet while an open chat exists", () => {
    expect(inboxEmptyState(1, 4)).toBeNull();
  });
});

describe("filterBots", () => {
  const bots = [
    { name: "Research", title: "web", preview: "opened zara" },
    { name: "Ops", title: "alerts", preview: "disk ok" },
  ];

  it("filters by name and preview", () => {
    expect(filterBots(bots, "zara", (bot) => bot.preview || bot.title || "").map((bot) => bot.name)).toEqual([
      "Research",
    ]);
    expect(filterBots(bots, "OPS", (bot) => bot.preview || bot.title || "").map((bot) => bot.name)).toEqual([
      "Ops",
    ]);
  });

  it("returns everyone when the query is blank", () => {
    expect(filterBots(bots, "  ", (bot) => bot.preview || "")).toHaveLength(2);
  });
});
