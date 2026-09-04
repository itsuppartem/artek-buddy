export type PhoneTab = "today" | "chats" | "chat" | "desk" | "more";

export const PHONE_BREAKPOINT_PX = 720;
export const PHONE_LANDSCAPE_MAX_HEIGHT_PX = 480;
export const DESKTOP_MIN_WIDTH_PX = 1280;

export function nextPhoneTab(
  action:
    | "select-bot"
    | "open-today"
    | "open-chats"
    | "open-chat"
    | "open-desk"
    | "open-more"
    | "close-desk",
): PhoneTab {
  if (action === "open-today") return "today";
  if (action === "open-chats") return "chats";
  if (action === "open-desk") return "desk";
  if (action === "open-more") return "more";
  return "chat";
}

export function phoneTabAfterPanel(panel: string | null | undefined): PhoneTab {
  if (panel === "computer") return "desk";
  if (panel) return "more";
  return "chat";
}

export function shouldUsePhoneShell(width: number, height = width): boolean {
  if (width <= PHONE_BREAKPOINT_PX) {
    return true;
  }
  return height <= PHONE_LANDSCAPE_MAX_HEIGHT_PX && width < DESKTOP_MIN_WIDTH_PX;
}

/** Pad when the pointer is coarse. A mouse desktop uses the .deb overlay even if the window is narrow. */
export function shouldUsePhoneDeskControls(mouseDesktop: boolean): boolean {
  return !mouseDesktop;
}
