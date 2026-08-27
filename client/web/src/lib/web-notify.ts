import type { AttentionAlert } from "./alerts";
import { shouldSendDesktopAlert } from "./alerts";

export type PageSurface = "desktop" | "host";

let surface: PageSurface = "desktop";

export function setPageSurface(next: PageSurface): void {
  surface = next;
}

export function pageSurface(): PageSurface {
  return surface;
}

export function pairAgainLabel(surface: PageSurface = pageSurface()): string {
  return surface === "host" ? "Pair this phone again" : "Pair this computer again";
}

export function isStandaloneDisplay(): boolean {
  if (typeof window === "undefined") return false;
  const nav = window.navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true;
}

export function isIosDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

export function shouldShowHomeScreenHint(input: {
  surface: PageSurface;
  ios: boolean;
  standalone: boolean;
}): boolean {
  return input.surface === "host" && input.ios && !input.standalone;
}

export function shouldOfferWebAlerts(input: {
  surface: PageSurface;
  permission: NotificationPermission | "unsupported";
  standalone: boolean;
  ios: boolean;
}): "hide" | "ask" | "ready" {
  if (input.surface !== "host") return "hide";
  if (input.permission === "unsupported" || input.permission === "denied") return "hide";
  if (input.ios && !input.standalone) return "hide";
  if (input.permission === "granted") return "ready";
  return "ask";
}

export function shouldShowWebNotification(input: {
  pageHidden: boolean;
  viewingBotId: string | null;
  alertBotId: string;
}): boolean {
  return shouldSendDesktopAlert({
    windowFocused: !input.pageHidden,
    viewingBotId: input.viewingBotId,
    alertBotId: input.alertBotId,
  });
}

export function shouldHoldHostAlert(input: {
  pageHidden: boolean;
  viewingBotId: string | null;
  alertBotId: string;
}): boolean {
  const banner = shouldSendDesktopAlert({
    windowFocused: true,
    viewingBotId: input.viewingBotId,
    alertBotId: input.alertBotId,
  });
  const web = shouldShowWebNotification(input);
  return !banner && !web;
}

export function webNotificationBody(alert: AttentionAlert): string {
  return alert.body || alert.title;
}
