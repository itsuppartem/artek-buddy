import { describe, expect, it } from "vitest";
import { isRawRunFailed, ownerRunError, TURN_FAILED } from "./run-error";

describe("ownerRunError", () => {
  it("hides a raw run failed id", () => {
    const raw = "run failed: run-fb7fd73f-32ed-43ed-a22f-a561aab1600a";
    expect(isRawRunFailed(raw)).toBe(true);
    expect(ownerRunError(raw, "failed")).toBe(TURN_FAILED);
    expect(ownerRunError("scripted fail", "failed")).toBe("scripted fail");
    expect(ownerRunError(undefined, "cancelled")).toBe("Stopped.");
  });
});
