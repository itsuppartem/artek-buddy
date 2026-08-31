import { describe, expect, it } from "vitest";
import {
  defaultMemoryScope,
  memoryChapter,
  memoryDeleteName,
  memoryKind,
  memoryShelf,
} from "./memory";

describe("memory chapter labels", () => {
  it("labels owner place and person as identity", () => {
    expect(memoryChapter("entries/owner/place-ment_1.md")).toBe("identity");
    expect(memoryChapter("entries/owner/person-ment_1.md")).toBe("identity");
    expect(memoryKind("entries/owner/place-ment_1.md")).toBe("place");
    expect(memoryShelf("entries/owner/place-ment_1.md")).toBe("owner");
    expect(memoryChapter("entries/charter/rule-ment_1.md")).toBe("rule");
    expect(memoryChapter("entries/owner/note-1.md")).toBe("note");
  });

  it("defaults a new card on this bot and names delete as a verb", () => {
    expect(defaultMemoryScope()).toBe("bot");
    expect(memoryDeleteName()).toBe("Remove");
  });
});
