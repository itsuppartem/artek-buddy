import { describe, expect, it } from "vitest";
import { artifactUrl, formatBytes, usesBrowserDownload } from "./files";

describe("formatBytes", () => {
  it("formats bytes, KB, and MB", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(20 * 1024)).toBe("20 KB");
    expect(formatBytes(2.5 * 1024 * 1024)).toBe("2.5 MB");
  });
});

describe("artifactUrl", () => {
  it("builds a host path and encodes the id", () => {
    expect(artifactUrl("ab/c")).toBe("/v1/artifacts/ab%2Fc");
  });
});

describe("usesBrowserDownload", () => {
  it("uses the browser on the host page, not the Linux save path", () => {
    expect(usesBrowserDownload("host")).toBe(true);
    expect(usesBrowserDownload("desktop")).toBe(false);
  });
});
