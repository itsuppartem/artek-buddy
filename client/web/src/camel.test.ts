import { describe, expect, it } from "vitest";
import { camelize, snakify } from "./camel";

describe("camelize", () => {
  it("walks objects and arrays", () => {
    expect(
      camelize({
        bot_id: "bot_1",
        older_cursor: 3,
        nested: { run_id: "run_1" },
        items: [{ thread_id: "th_1" }],
      }),
    ).toEqual({
      botId: "bot_1",
      olderCursor: 3,
      nested: { runId: "run_1" },
      items: [{ threadId: "th_1" }],
    });
  });

  it("leaves event type strings alone", () => {
    expect(camelize({ type: "thread.message.updated" })).toEqual({
      type: "thread.message.updated",
    });
  });
});

describe("snakify", () => {
  it("round-trips create-bot input", () => {
    expect(snakify({ computerMode: "team", notifyOnFinish: true })).toEqual({
      computer_mode: "team",
      notify_on_finish: true,
    });
  });
});
