import { describe, expect, it } from "vitest";
import { formatMemoryExport, isMemoryPath } from "./memory";

describe("isMemoryPath", () => {
  it("accepts a relative document name", () => {
    expect(isMemoryPath("MEMORY.md")).toBe(true);
    expect(isMemoryPath("notes/foo.md")).toBe(true);
  });

  it("rejects parent paths", () => {
    expect(isMemoryPath("")).toBe(false);
    expect(isMemoryPath("../secret")).toBe(false);
    expect(isMemoryPath("/etc/passwd")).toBe(false);
  });
});

describe("formatMemoryExport", () => {
  it("joins documents as markdown", () => {
    expect(formatMemoryExport([{ path: "MEMORY.md", content: "likes tea" }])).toBe(
      "# MEMORY.md\n\nlikes tea",
    );
    expect(formatMemoryExport([])).toBe("");
  });
});
