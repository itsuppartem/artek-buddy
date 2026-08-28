import { describe, expect, it } from "vitest";
import { filterBots, inboxEmptyState, sortInboxBots, splitQueryMatch } from "./sidebar";

describe("inboxEmptyState", () => {
  it("is create when both lists are empty", () => {
    expect(inboxEmptyState(0, 0)).toBe("create");
  });

  it("points at archived when inbox is empty", () => {
    expect(inboxEmptyState(0, 2)).toBe("archived");
  });

  it("is null when the inbox has rows", () => {
    expect(inboxEmptyState(1, 9)).toBeNull();
  });
});

describe("sortInboxBots", () => {
  it("pins first, then createdAt, then id", () => {
    const bots = [
      { id: "b", pinned: false, createdAt: "2026-01-02" },
      { id: "a", pinned: false, createdAt: "2026-01-02" },
      { id: "z", pinned: true, createdAt: "2026-01-03" },
    ];
    expect(sortInboxBots(bots).map((bot) => bot.id)).toEqual(["z", "a", "b"]);
  });
});

describe("filterBots", () => {
  it("matches name or preview, case-insensitive", () => {
    const bots = [
      { name: "Alpha", preview: "hello" },
      { name: "Beta", preview: "world" },
    ];
    expect(filterBots(bots, "ALP", (bot) => bot.preview).map((bot) => bot.name)).toEqual(["Alpha"]);
    expect(filterBots(bots, "wor", (bot) => bot.preview).map((bot) => bot.name)).toEqual(["Beta"]);
  });
});

describe("splitQueryMatch", () => {
  it("marks the first preview hit so a snippet match is visible", () => {
    expect(splitQueryMatch("Research: Novi Sad", "res")).toEqual([
      { text: "Res", hit: true },
      { text: "earch: Novi Sad", hit: false },
    ]);
    expect(splitQueryMatch("Lead", "res")).toEqual([{ text: "Lead", hit: false }]);
  });
});
