import { describe, expect, it } from "vitest";
import { isCronShape } from "./cron";

describe("isCronShape", () => {
  it("accepts five whitespace-separated fields", () => {
    expect(isCronShape("0 9 * * *")).toBe(true);
    expect(isCronShape("  */5  *   * * 1 ")).toBe(true);
  });

  it("rejects anything else", () => {
    expect(isCronShape("")).toBe(false);
    expect(isCronShape("0 9 * *")).toBe(false);
    expect(isCronShape("0 9 * * * extra")).toBe(false);
  });
});
