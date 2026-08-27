import { describe, expect, it } from "vitest";
import { memoryChapter, memoryKind, memoryShelf } from "./memory";

describe("memory chapter labels", () => {
  it("labels owner place and person as identity", () => {
    expect(memoryChapter("entries/owner/place-ment_1.md")).toBe("identity");
    expect(memoryChapter("entries/owner/person-ment_1.md")).toBe("identity");
    expect(memoryKind("entries/owner/place-ment_1.md")).toBe("place");
    expect(memoryShelf("entries/owner/place-ment_1.md")).toBe("owner");
    expect(memoryChapter("entries/charter/rule-ment_1.md")).toBe("rule");
    expect(memoryChapter("entries/owner/note-1.md")).toBe("note");
  });
});
