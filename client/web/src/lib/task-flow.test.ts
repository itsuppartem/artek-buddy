import { describe, expect, it } from "vitest";
import { botTaskStage } from "./task-flow";

describe("task-first routing", () => {
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
