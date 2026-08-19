import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";

const saveArtifact = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      ...actual.api,
      local: {
        ...actual.api.local,
        saveArtifact: (...args: unknown[]) => saveArtifact(...args),
      },
    },
  };
});

const { DownloadCancelled, downloadArtifact, formatBytes } = await import("./files");

describe("formatBytes", () => {
  it("formats sizes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(20 * 1024)).toBe("20 KB");
    expect(formatBytes(2.5 * 1024 * 1024)).toBe("2.5 MB");
  });
});

describe("downloadArtifact — .deb write path", () => {
  beforeEach(() => {
    saveArtifact.mockReset();
  });

  it("returns the path Python wrote and never synthesizes a click", async () => {
    saveArtifact.mockResolvedValue({ ok: true, path: "/home/me/Загрузки/notes.txt" });
    await expect(downloadArtifact("art_1", "notes.txt")).resolves.toEqual({
      path: "/home/me/Загрузки/notes.txt",
    });
    expect(saveArtifact).toHaveBeenCalledWith({ artifactId: "art_1", name: "notes.txt" });
    expect(saveArtifact).toHaveBeenCalledTimes(1);
  });

  it("does not claim Saved to when the loopback write fails", async () => {
    saveArtifact.mockRejectedValue(new ApiError("Could not write the file", 500));
    await expect(downloadArtifact("art_1", "notes.txt")).rejects.toThrow(/Could not/);
  });

  it("does not fall through to a silent <a download> on 404", async () => {
    saveArtifact.mockRejectedValue(new ApiError("Could not download that file", 404));
    await expect(downloadArtifact("art_1", "notes.txt")).rejects.toThrow(/Could not download/);
    expect(saveArtifact).toHaveBeenCalledTimes(1);
  });

  it("rejects an empty artifact id", async () => {
    await expect(downloadArtifact("", "notes.txt")).rejects.toThrow(/Could not download/);
    expect(saveArtifact).not.toHaveBeenCalled();
  });

  it("treats a cancelled Save dialog as not saved", async () => {
    saveArtifact.mockRejectedValue(new ApiError("Save cancelled", 409));
    await expect(downloadArtifact("art_1", "notes.txt")).rejects.toBeInstanceOf(DownloadCancelled);
  });
});
