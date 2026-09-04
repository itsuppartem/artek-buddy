import { describe, expect, it, vi } from "vitest";
import {
  applyThemePreference,
  parseThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
} from "./theme";

describe("appearance preference", () => {
  it("accepts only system, light, or dark", () => {
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("dark")).toBe("dark");
    expect(parseThemePreference("system")).toBe("system");
    expect(parseThemePreference("midnight")).toBe("system");
    expect(parseThemePreference(null)).toBe("system");
  });

  it("uses the Ubuntu preference only in system mode", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("applies and persists a manual preference", () => {
    const root = { dataset: {} as Record<string, string> };
    const storage = { setItem: vi.fn() };

    applyThemePreference("dark", root, storage);

    expect(root.dataset.theme).toBe("dark");
    expect(storage.setItem).toHaveBeenCalledWith(THEME_STORAGE_KEY, "dark");
  });
});
