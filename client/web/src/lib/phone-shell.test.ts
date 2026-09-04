import { describe, expect, it } from "vitest";
import {
  nextPhoneTab,
  phoneTabAfterPanel,
  shouldUsePhoneDeskControls,
  shouldUsePhoneShell,
} from "./phone-shell";

describe("phone shell tabs", () => {
  it("keeps Today and More one tap away around chat and desktop", () => {
    expect(nextPhoneTab("open-today")).toBe("today");
    expect(nextPhoneTab("select-bot")).toBe("chat");
    expect(nextPhoneTab("open-desk")).toBe("desk");
    expect(nextPhoneTab("open-chats")).toBe("chats");
    expect(nextPhoneTab("open-chat")).toBe("chat");
    expect(nextPhoneTab("open-more")).toBe("more");
    expect(nextPhoneTab("close-desk")).toBe("chat");
    expect(phoneTabAfterPanel(null)).toBe("chat");
    expect(phoneTabAfterPanel("models")).toBe("more");
    expect(phoneTabAfterPanel("plugins")).toBe("more");
    expect(phoneTabAfterPanel("library")).toBe("more");
    expect(phoneTabAfterPanel("routines")).toBe("more");
    expect(phoneTabAfterPanel("worklog")).toBe("more");
    expect(phoneTabAfterPanel("computer")).toBe("desk");
  });

  it("uses the stacked shell at phone width only", () => {
    expect(shouldUsePhoneShell(375)).toBe(true);
    expect(shouldUsePhoneShell(390)).toBe(true);
    expect(shouldUsePhoneShell(720)).toBe(true);
    expect(shouldUsePhoneShell(721)).toBe(false);
    expect(shouldUsePhoneShell(812, 375)).toBe(true);
    expect(shouldUsePhoneShell(1280, 720)).toBe(false);
    expect(shouldUsePhoneShell(1280, 800)).toBe(false);
  });

  it("uses the phone pad only when there is no mouse desktop", () => {
    expect(shouldUsePhoneDeskControls(true)).toBe(false);
    expect(shouldUsePhoneDeskControls(false)).toBe(true);
  });
});
