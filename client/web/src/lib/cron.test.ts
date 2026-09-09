import { describe, expect, it } from "vitest";
import { formatNextRunAt, isCronShape } from "./cron";

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

describe("formatNextRunAt", () => {
  it("drops the ISO fraction and keeps UTC", () => {
    expect(formatNextRunAt("2026-08-31T09:30:00.000000Z")).toBe("2026-08-31 09:30:00 UTC");
    expect(formatNextRunAt("2026-08-31T09:30:00.000000Z")).not.toContain(".000000");
  });
});
