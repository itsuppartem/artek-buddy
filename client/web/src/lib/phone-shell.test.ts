import { describe, expect, it } from "vitest";
import { nextPhoneTab, shouldUsePhoneShell } from "./phone-shell";

describe("phone shell tabs", () => {
  it("opens chat after picking a bot and desk after Computer", () => {
    expect(nextPhoneTab("select-bot")).toBe("chat");
    expect(nextPhoneTab("open-desk")).toBe("desk");
    expect(nextPhoneTab("open-chats")).toBe("chats");
    expect(nextPhoneTab("open-chat")).toBe("chat");
  });

  it("uses the stacked shell at phone width only", () => {
    expect(shouldUsePhoneShell(375)).toBe(true);
    expect(shouldUsePhoneShell(390)).toBe(true);
    expect(shouldUsePhoneShell(720)).toBe(true);
    expect(shouldUsePhoneShell(721)).toBe(false);
  });
});
