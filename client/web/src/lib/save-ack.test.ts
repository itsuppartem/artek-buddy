import { describe, expect, it } from "vitest";
import { saveButtonLabel, storeButtonLabel } from "./save-ack";

describe("saveButtonLabel", () => {
  it("names idle, saving, and saved", () => {
    expect(saveButtonLabel("idle")).toBe("Save");
    expect(saveButtonLabel("saving")).toBe("Saving…");
    expect(saveButtonLabel("saved")).toBe("Saved");
  });
});

describe("storeButtonLabel", () => {
  it("does not reuse the profile Save name", () => {
    expect(storeButtonLabel("idle")).toBe("Store");
    expect(storeButtonLabel("saving")).toBe("Storing…");
    expect(storeButtonLabel("saved")).toBe("Stored");
  });
});
