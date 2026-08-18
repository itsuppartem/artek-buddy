import type { DesktopBridge } from "../types";

export function desktopBridge(): DesktopBridge | undefined {
  return typeof window === "undefined" ? undefined : window.artekDesktop;
}

export function windowChromeKind(desktop?: DesktopBridge): "spacer" | "darwin" | "controls" {
  if (!desktop) return "spacer";
  if (desktop.platform === "darwin") return "darwin";
  return "controls";
}
