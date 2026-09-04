import { describe, expect, it } from "vitest";
import { botTaskStage, suggestTaskBot } from "./task-flow";

const bots = [
  {
    id: "mail",
    name: "Mail",
    title: "Inbox and replies",
    description: "Reads messages and prepares email",
    instructions: "",
    pinned: false,
    status: "idle",
    unread: false,
    preview: "",
  },
  {
    id: "release",
    name: "Release helper",
    title: "Packages and releases",
    description: "Verifies builds and release notes",
    instructions: "",
    pinned: false,
    status: "idle",
    unread: false,
    preview: "",
  },
  {
    id: "home",
    name: "Home admin",
    title: "General help",
    description: "",
    instructions: "",
    pinned: true,
    status: "idle",
    unread: false,
    preview: "",
  },
];

describe("task-first routing", () => {
  it("suggests the bot whose purpose overlaps the requested outcome", () => {
    expect(suggestTaskBot(bots, "Verify the release package and prepare release notes")?.id).toBe(
      "release",
    );
    expect(suggestTaskBot(bots, "Draft a reply to the vendor email")?.id).toBe("mail");
  });

  it("falls back to a pinned bot when the task has no meaningful overlap", () => {
    expect(suggestTaskBot(bots, "Help me think this through")?.id).toBe("home");
  });

  it("puts decisions before work and ready results", () => {
    expect(
      botTaskStage({ status: "waiting", unread: true, preview: "Needs approval to send" }),
    ).toBe("decision");
    expect(
      botTaskStage({ status: "waiting_input", unread: false, preview: "Choose a delivery window" }),
    ).toBe("decision");
    expect(botTaskStage({ status: "working", unread: false, preview: "Reading source 3" })).toBe(
      "working",
    );
    expect(botTaskStage({ status: "idle", unread: true, preview: "Report is ready" })).toBe(
      "ready",
    );
    expect(botTaskStage({ status: "idle", unread: false, preview: "Sleeping" })).toBe("recent");
  });
});
