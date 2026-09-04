export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "artek-theme";
export const THEME_CHANGE_EVENT = "artek-theme-change";

type ThemeRoot = {
  dataset: Record<string, string> | DOMStringMap;
};

export function parseThemePreference(value: string | null): ThemePreference {
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

export function resolveTheme(
  preference: ThemePreference,
  systemPrefersDark: boolean,
): ResolvedTheme {
  if (preference === "system") return systemPrefersDark ? "dark" : "light";
  return preference;
}

export function readThemePreference(storage?: Pick<Storage, "getItem">): ThemePreference {
  const target = storage ?? (typeof window === "undefined" ? undefined : window.localStorage);
  if (!target) return "system";
  try {
    return parseThemePreference(target.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

export function applyThemePreference(
  preference: ThemePreference,
  root?: ThemeRoot,
  storage?: Pick<Storage, "setItem">,
): void {
  const targetRoot =
    root ?? (typeof document === "undefined" ? undefined : document.documentElement);
  const targetStorage =
    storage ?? (typeof window === "undefined" ? undefined : window.localStorage);

  if (targetRoot) targetRoot.dataset.theme = preference;
  try {
    targetStorage?.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // A restricted browser can still keep the theme for this page.
  }

  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
  }
}
