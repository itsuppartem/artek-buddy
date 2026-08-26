export type PhoneTab = "chats" | "chat" | "desk";

export const PHONE_BREAKPOINT_PX = 720;

export function nextPhoneTab(
  action: "select-bot" | "open-chats" | "open-chat" | "open-desk",
): PhoneTab {
  if (action === "open-chats") return "chats";
  if (action === "open-desk") return "desk";
  return "chat";
}

export function shouldUsePhoneShell(width: number, height = width): boolean {
  return Math.min(width, height) <= PHONE_BREAKPOINT_PX;
}
