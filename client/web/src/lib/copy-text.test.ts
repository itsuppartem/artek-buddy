import { describe, expect, it, vi } from "vitest";
import { copyText } from "./copy-text";

describe("copyText", () => {
  it("uses the modern clipboard API when available", async () => {
    const writeText = vi.fn(async () => undefined);
    const fallback = vi.fn(() => true);

    await expect(copyText("https://example.com", { writeText, fallback })).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("https://example.com");
    expect(fallback).not.toHaveBeenCalled();
  });

  it("falls back when WebKit clipboard writing is unavailable", async () => {
    const writeText = vi.fn(async () => {
      throw new Error("not allowed");
    });
    const fallback = vi.fn(() => true);

    await expect(copyText("https://example.com", { writeText, fallback })).resolves.toBe(true);
    expect(fallback).toHaveBeenCalledWith("https://example.com");
  });
});
