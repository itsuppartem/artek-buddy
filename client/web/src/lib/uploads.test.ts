import { describe, expect, it, vi } from "vitest";
import {
  MAX_UPLOAD_FILE_BYTES,
  addPendingFiles,
  clipboardFilePaths,
  clipboardHasAttachable,
  filesFromAttachedPayload,
  nameClipboardFile,
  normalizeClipboardPath,
  pastedFiles,
  previewKind,
  readClipboardFiles,
} from "./uploads";

function file(name: string, size: number, type = "text/plain"): File {
  const data = new Uint8Array(size);
  return new File([data], name, { type });
}

function fileList(files: File[]): FileList {
  const list: Record<number, File> & {
    length: number;
    item: (index: number) => File | null;
  } = {
    length: files.length,
    item: (index: number) => files[index] ?? null,
  };
  files.forEach((entry, index) => {
    list[index] = entry;
  });
  return list as unknown as FileList;
}

describe("addPendingFiles", () => {
  it("accepts several files and rejects a 11th", () => {
    const first = addPendingFiles(
      [],
      Array.from({ length: 10 }, (_, i) => file(`n${i}.txt`, 4)),
    );
    expect(first.error).toBe("");
    expect(first.files).toHaveLength(10);
    const extra = addPendingFiles(first.files, [file("more.txt", 4)]);
    expect(extra.error).toMatch(/At most 10/);
    expect(extra.files).toHaveLength(10);
  });

  it("rejects an empty file", () => {
    const out = addPendingFiles([], [file("empty.txt", 0)]);
    expect(out.error).toMatch(/Empty/);
    expect(out.files).toHaveLength(0);
  });

  it("keeps a clipboard image even when size reports 0", () => {
    const shot = new File([], "", { type: "image/png" });
    const out = addPendingFiles([], [nameClipboardFile(shot, 0)]);
    expect(out.error).toBe("");
    expect(out.files).toHaveLength(1);
    expect(out.files[0].file.name).toBe("screenshot-1.png");
  });

  it("rejects a file over 25 MB and does not keep a partial pile", () => {
    const out = addPendingFiles([], [file("huge.bin", MAX_UPLOAD_FILE_BYTES + 1)]);
    expect(out.error).toMatch(/larger than 25 MB/);
    expect(out.files).toHaveLength(0);
  });

  it("rejects a pile over 50 MB together", () => {
    const first = addPendingFiles(
      [],
      [file("a.bin", 20 * 1024 * 1024), file("b.bin", 20 * 1024 * 1024)],
    );
    expect(first.error).toBe("");
    const extra = addPendingFiles(first.files, [file("c.bin", 15 * 1024 * 1024)]);
    expect(extra.error).toMatch(/too large together/);
    expect(extra.files).toHaveLength(2);
  });
});

describe("previewKind", () => {
  it("classifies by mime and extension", () => {
    expect(previewKind(new File([new Uint8Array(4)], "a.png", { type: "image/png" }))).toBe("image");
    expect(previewKind(new File([new Uint8Array(4)], "clip.mp4", { type: "video/mp4" }))).toBe("video");
    expect(previewKind(new File([new Uint8Array(4)], "voice.mp3", { type: "audio/mpeg" }))).toBe("audio");
    expect(previewKind(new File([new Uint8Array(4)], "notes.txt", { type: "text/plain" }))).toBe("file");
  });
});

describe("pastedFiles", () => {
  it("reads clipboard files", () => {
    const item = file("shot.png", 8, "image/png");
    expect(
      pastedFiles({ clipboardData: { files: fileList([item]), items: [] } as unknown as DataTransfer }),
    ).toHaveLength(1);
  });

  it("reads a screenshot from items when files is empty", () => {
    const shot = new File([new Uint8Array([137, 80, 78, 71])], "", { type: "image/png" });
    const files = pastedFiles({
      clipboardData: {
        files: fileList([]),
        items: [{ kind: "file", type: "image/png", getAsFile: () => shot }],
      } as unknown as DataTransfer,
    });
    expect(files).toHaveLength(1);
    expect(files[0].name).toBe("screenshot-1.png");
    expect(files[0].type).toBe("image/png");
  });

  it("returns nothing when WebKit has not hydrated getAsFile yet", () => {
    const files = pastedFiles({
      clipboardData: {
        files: fileList([]),
        items: [{ kind: "file", type: "image/png", getAsFile: () => null }],
      } as unknown as DataTransfer,
    });
    expect(files).toHaveLength(0);
    expect(
      clipboardHasAttachable({
        clipboardData: {
          files: fileList([]),
          items: [{ kind: "file", type: "image/png", getAsFile: () => null }],
        } as unknown as DataTransfer,
      }),
    ).toBe(true);
  });

  it("reads an image item even when kind is not file", () => {
    const shot = new File([new Uint8Array([1, 2, 3, 4])], "", { type: "image/png" });
    const files = pastedFiles({
      clipboardData: {
        files: fileList([]),
        items: [{ kind: "string", type: "image/png", getAsFile: () => shot }],
      } as unknown as DataTransfer,
    });
    expect(files[0]?.name).toBe("screenshot-1.png");
  });

  it("does not double-count the same File from files and items", () => {
    const shot = file("shot.png", 8, "image/png");
    const files = pastedFiles({
      clipboardData: {
        files: fileList([shot]),
        items: [{ kind: "file", type: "image/png", getAsFile: () => shot }],
      } as unknown as DataTransfer,
    });
    expect(files).toHaveLength(1);
  });
});

describe("clipboardFilePaths", () => {
  it("reads file:// URIs and gnome copied-files", () => {
    const path = "/home/artek/Изображения/Снимки экрана/shot.jpeg";
    expect(
      clipboardFilePaths({
        clipboardData: {
          files: fileList([]),
          items: [],
          getData: (type: string) =>
            type === "text/uri-list" ? `file://${encodeURI(path)}` : "",
        } as unknown as DataTransfer,
      }),
    ).toEqual([path]);
    expect(
      clipboardFilePaths({
        clipboardData: {
          files: fileList([]),
          items: [],
          getData: (type: string) =>
            type === "x-special/gnome-copied-files" ? `copy\nfile://${encodeURI(path)}` : "",
        } as unknown as DataTransfer,
      }),
    ).toEqual([path]);
  });

  it("treats a clipboard that is only an absolute path as a file", () => {
    const path = "/home/artek/Документы/notes.pdf";
    expect(
      clipboardFilePaths({
        clipboardData: {
          files: fileList([]),
          items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
          getData: (type: string) => (type === "text/plain" ? path : ""),
        } as unknown as DataTransfer,
      }),
    ).toEqual([path]);
  });

  it("does not steal a sentence that happens to mention a path", () => {
    expect(
      clipboardFilePaths({
        clipboardData: {
          files: fileList([]),
          items: [],
          getData: (type: string) =>
            type === "text/plain" ? "look at /home/artek/shot.jpeg please" : "",
        } as unknown as DataTransfer,
      }),
    ).toEqual([]);
    expect(
      clipboardHasAttachable({
        clipboardData: {
          files: fileList([]),
          items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
          getData: (type: string) =>
            type === "text/plain" ? "look at /home/artek/shot.jpeg please" : "",
        } as unknown as DataTransfer,
      }),
    ).toBe(false);
  });

  it("normalizes localhost file URLs and quoted paths", () => {
    expect(normalizeClipboardPath('file://localhost/home/artek/a.png')).toBe("/home/artek/a.png");
    expect(normalizeClipboardPath('"/home/artek/a.png"')).toBe("/home/artek/a.png");
    expect(normalizeClipboardPath("~/Pictures/a.png")).toBe("~/Pictures/a.png");
  });

  it("rebuilds a File from the local attach payload", () => {
    const files = filesFromAttachedPayload([
      { name: "shot.jpeg", type: "image/jpeg", contentBase64: btoa("jpeg-bytes") },
    ]);
    expect(files).toHaveLength(1);
    expect(files[0].name).toBe("shot.jpeg");
    expect(files[0].type).toBe("image/jpeg");
  });
});

describe("clipboardHasAttachable", () => {
  it("is true for an image item before getAsFile runs", () => {
    expect(
      clipboardHasAttachable({
        clipboardData: {
          files: fileList([]),
          items: [{ kind: "file", type: "image/png", getAsFile: () => null }],
        } as unknown as DataTransfer,
      }),
    ).toBe(true);
  });

  it("is false for plain text", () => {
    expect(
      clipboardHasAttachable({
        clipboardData: {
          files: fileList([]),
          items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
          getData: () => "hello there",
        } as unknown as DataTransfer,
      }),
    ).toBe(false);
  });

  it("is true for a file-manager path so Ctrl+V is not inserted as text", () => {
    expect(
      clipboardHasAttachable({
        clipboardData: {
          files: fileList([]),
          items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
          getData: (type: string) =>
            type === "text/plain" ? "/home/artek/Изображения/Снимки экрана/a.jpeg" : "",
        } as unknown as DataTransfer,
      }),
    ).toBe(true);
  });

  it("is false when the clipboard is empty so Ctrl+V of text is not stolen", () => {
    expect(clipboardHasAttachable({ clipboardData: null })).toBe(false);
    expect(
      clipboardHasAttachable({
        clipboardData: { files: fileList([]), items: [] } as unknown as DataTransfer,
      }),
    ).toBe(false);
  });
});

describe("readClipboardFiles", () => {
  it("falls back to navigator.clipboard.read when paste items are empty", async () => {
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: "image/png" });
    vi.stubGlobal("navigator", {
      clipboard: {
        read: async () => [{ types: ["image/png"], getType: async () => blob }],
      },
    });
    try {
      const files = await readClipboardFiles({
        clipboardData: { files: fileList([]), items: [] } as unknown as DataTransfer,
      });
      expect(files).toHaveLength(1);
      expect(files[0].name).toBe("screenshot-1.png");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
