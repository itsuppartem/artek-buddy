import { describe, expect, it } from "vitest";
import { camelize, snakify } from "./camel";

describe("camelize", () => {
  it("turns snake_case object keys into camelCase", () => {
    expect(camelize({ bot_id: "b1", nested: { thread_id: "t1" } })).toEqual({
      botId: "b1",
      nested: { threadId: "t1" },
    });
  });

  it("walks arrays", () => {
    expect(camelize([{ run_id: "r1" }])).toEqual([{ runId: "r1" }]);
  });
});

describe("snakify", () => {
  it("turns camelCase object keys into snake_case", () => {
    expect(snakify({ botId: "b1", nested: { threadId: "t1" } })).toEqual({
      bot_id: "b1",
      nested: { thread_id: "t1" },
    });
  });
});
