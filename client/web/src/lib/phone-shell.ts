export type PhoneTab = "chats" | "chat" | "desk";

export const PHONE_BREAKPOINT_PX = 720;
export const PHONE_LANDSCAPE_MAX_HEIGHT_PX = 480;
export const DESKTOP_MIN_WIDTH_PX = 1280;

export function nextPhoneTab(
  action: "select-bot" | "open-chats" | "open-chat" | "open-desk" | "close-desk",
): PhoneTab {
  if (action === "open-chats") return "chats";
  if (action === "open-desk") return "desk";
  return "chat";
}

const DESK_PANELS = new Set(["computer", "models", "plugins", "settings", "create"]);

export function phoneTabAfterPanel(panel: string | null | undefined): PhoneTab {
  return panel && DESK_PANELS.has(panel) ? "desk" : "chat";
}

export function shouldUsePhoneShell(width: number, height = width): boolean {
  if (width <= PHONE_BREAKPOINT_PX) {
    return true;
  }
  return height <= PHONE_LANDSCAPE_MAX_HEIGHT_PX && width < DESKTOP_MIN_WIDTH_PX;
}
