import { describe, expect, it } from "vitest";
import { composerCanSend, composerPlaceholder } from "./composer";

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

describe("composerPlaceholder", () => {
  it("keeps a short name in full", () => {
    expect(composerPlaceholder("Demo")).toBe("Message Demo");
  });

  it("truncates a long name with an ellipsis instead of a mid-word clip", () => {
    const name = "ResearchOverflowName";
    const placeholder = composerPlaceholder(name);
    expect(placeholder.startsWith("Message ")).toBe(true);
    expect(placeholder.endsWith("…")).toBe(true);
    expect(placeholder).not.toBe("Message Resea");
    expect(placeholder).not.toBe(`Message ${name}`);
    expect(`Message ${name}`.startsWith(placeholder)).toBe(false);
  });
});
