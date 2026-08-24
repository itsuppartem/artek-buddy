import { describe, expect, it } from "vitest";
import { composerCanSend } from "./composer";

describe("composerCanSend", () => {
  it("disables send when there is no text and no files", () => {
    expect(composerCanSend("", 0)).toBe(false);
    expect(composerCanSend("   ", 0)).toBe(false);
  });

  it("enables send when there is text or a file", () => {
    expect(composerCanSend("hello", 0)).toBe(true);
    expect(composerCanSend("", 1)).toBe(true);
  });
});
