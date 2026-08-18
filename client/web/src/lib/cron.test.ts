import { describe, expect, it } from "vitest";
import { isCronShape } from "./cron";

describe("isCronShape", () => {
  it("accepts five fields", () => {
    expect(isCronShape("0 9 * * *")).toBe(true);
    expect(isCronShape("*/5 * * * *")).toBe(true);
  });

  it("rejects other shapes", () => {
    expect(isCronShape("")).toBe(false);
    expect(isCronShape("0 9 * *")).toBe(false);
    expect(isCronShape("every morning")).toBe(false);
  });
});
