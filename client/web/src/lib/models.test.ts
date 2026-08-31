import { describe, expect, it } from "vitest";
import {
  defaultModelValue,
  MODEL_PROVIDERS,
  maskedKey,
  modelChipSelected,
  NEEDS_MODEL_TEXT,
  parseDefaultModelValue,
} from "./models";

describe("models copy and values", () => {
  it("names the five providers and the send next step", () => {
    expect(MODEL_PROVIDERS.map((item) => item.id)).toEqual([
      "cursor",
      "openrouter",
      "openai",
      "anthropic",
      "xai",
    ]);
    expect(NEEDS_MODEL_TEXT).toContain("Open Models");
  });

  it("round-trips the default model value and masks last four", () => {
    expect(defaultModelValue("openrouter", "scripted")).toBe("openrouter:scripted");
    expect(parseDefaultModelValue("openrouter:scripted")).toEqual({
      provider: "openrouter",
      model: "scripted",
    });
    expect(maskedKey("wxyz")).toBe("•••• wxyz");
    expect(maskedKey(null)).toBe("");
  });

  it("only the host default looks in use, not a local pick", () => {
    expect(modelChipSelected("grok-4.6", "gemini-2.5-flash")).toBe(false);
    expect(modelChipSelected("gemini-2.5-flash", "gemini-2.5-flash")).toBe(true);
    expect(modelChipSelected("", "grok-4.6")).toBe(false);
  });
});
