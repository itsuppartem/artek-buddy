import { describe, expect, it } from "vitest";
import { clipboardHasAttachable, clipboardShouldClaim, nameClipboardFile } from "./uploads";

function transfer(partial: {
  files?: File[];
  items?: Array<{ kind: string; type: string; getAsFile?: () => File | null }>;
  types?: string[];
  text?: string;
}): DataTransfer {
  const text = partial.text ?? "";
  return {
    files: (partial.files ?? []) as unknown as FileList,
    items: (partial.items ?? []) as unknown as DataTransferItemList,
    types: partial.types ?? [],
    getData: (type: string) => (type === "text/plain" || type === "text" ? text : ""),
  } as DataTransfer;
}

describe("clipboard paste", () => {
  it("treats a types-only image clipboard as attachable", () => {
    const event = { clipboardData: transfer({ types: ["image/png"], text: "" }) };
    expect(clipboardHasAttachable(event)).toBe(true);
    expect(clipboardShouldClaim(event)).toBe(true);
  });

  it("does not claim ordinary copied text", () => {
    const event = {
      clipboardData: transfer({ types: ["text/plain"], text: "hello from the clipboard" }),
    };
    expect(clipboardHasAttachable(event)).toBe(false);
    expect(clipboardShouldClaim(event)).toBe(false);
  });

  it("does not claim an empty WebKit clip and block native text paste", () => {
    const event = { clipboardData: transfer({ types: [], text: "" }) };
    expect(clipboardShouldClaim(event)).toBe(false);
  });

  it("does not claim a deferred WebKit text clip", () => {
    const event = { clipboardData: transfer({ types: ["text/plain"], text: "" }) };
    expect(clipboardShouldClaim(event)).toBe(false);
  });

  it("names an unnamed image clip screenshot-1.png", () => {
    const named = nameClipboardFile(
      new File([new Uint8Array([1, 2, 3])], "", { type: "image/png" }),
      0,
    );
    expect(named.name).toBe("screenshot-1.png");
    expect(named.type).toBe("image/png");
  });
});
