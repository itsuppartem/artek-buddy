import { describe, expect, it } from "vitest";
import { hatchIsOpen, hatchPointerEvents } from "./hatch";

describe("desk hatch", () => {
  it("is closed unless a pane is actually showing", () => {
    expect(hatchIsOpen(null, true)).toBe(false);
    expect(hatchIsOpen("plugins", false)).toBe(true);
    expect(hatchIsOpen("models", false)).toBe(true);
    expect(hatchIsOpen("create", false)).toBe(true);
    expect(hatchIsOpen("library", false)).toBe(true);
    expect(hatchIsOpen("settings", false)).toBe(false);
    expect(hatchIsOpen("settings", true)).toBe(true);
    expect(hatchIsOpen("computer", true)).toBe(true);
  });

  it("does not steal pointer or wheel while closed", () => {
    expect(hatchPointerEvents(false)).toBe("none");
    expect(hatchPointerEvents(true)).toBe("auto");
  });
});
