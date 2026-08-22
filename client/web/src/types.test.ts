import { describe, expectTypeOf, it } from "vitest";
import type { Bot, HealthResponse, MessageBlock } from "./types";

describe("OpenAPI-backed window types", () => {
  it("uses camelCase keys from the host schema", () => {
    expectTypeOf<Bot>().toHaveProperty("computerMode");
    expectTypeOf<Bot>().toHaveProperty("workspaceId");
    expectTypeOf<HealthResponse>().toHaveProperty("ok");
  });

  it("keeps block discriminators", () => {
    expectTypeOf<Extract<MessageBlock, { kind: "text" }>>().toHaveProperty("text");
  });
});
