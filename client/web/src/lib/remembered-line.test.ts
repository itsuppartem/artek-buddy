import { describe, expect, it } from "vitest";
import {
  memoryDocMatchesRemembered,
  rememberedLineKind,
  rememberedLinePreview,
} from "./remembered-line";

describe("rememberedLinePreview", () => {
  it("keeps a short Remembered line whole", () => {
    expect(rememberedLinePreview("Remembered: Prefers short answers")).toBe(
      "Remembered: Prefers short answers",
    );
  });

  it("cuts a long standing rule to one row with an ellipsis", () => {
    const text =
      "Remembered: RN-1935 P1 (biometric absent when Mesa not in boot syslog): stop. Do not change code, rebuild, reboot the phone, or pick error-vs-witness until the owner says so.";
    const preview = rememberedLinePreview(text, 72);
    expect(preview.endsWith("…")).toBe(true);
    expect(preview.length).toBeLessThanOrEqual(72);
    expect(preview.startsWith("Remembered: RN-1935")).toBe(true);
  });
});

describe("rememberedLineKind", () => {
  it("only Remembered and Forgot open Memory", () => {
    expect(rememberedLineKind("Remembered: Prefers short answers")).toBe("remembered");
    expect(rememberedLineKind("Forgot: old city")).toBe("forgot");
    expect(rememberedLineKind("Using scripted · Low · Fast.")).toBeNull();
  });
});

describe("memoryDocMatchesRemembered", () => {
  it("finds the Memory card from a Remembered fact, including a truncated clock line", () => {
    const card =
      "RN-1935 P1 (biometric absent when Mesa not in boot syslog): stop. Do not change code, rebuild, reboot the phone.";
    expect(memoryDocMatchesRemembered(card, card)).toBe(true);
    expect(memoryDocMatchesRemembered(card, card.slice(0, 72))).toBe(true);
    expect(memoryDocMatchesRemembered("GitHub login is personal", "RN-1935 P1")).toBe(false);
  });
});
